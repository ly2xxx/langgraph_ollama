"""Integration tests for the Phase 1 linear loop (coding_agent.engine).

These exercise the *real* graph, worktree lifecycle, self_check/bdd_gate
gates (real pytest/ruff subprocesses), diagnose routing, commit, and report
writer — everything except the two LLM call sites (`_llm_parse_target_spec`
and `_run_maker`), which are monkeypatched so the suite runs without a live
Ollama server. See CODING_ENGINEER.md and PHASED_PLAN.md for why those two
functions are the deliberate mock boundary.

`author_bdd` needs no mock here: the sample_target fixture already ships a
real features/calculator.feature, so author_bdd's "adopt existing" path
(no LLM call) is what actually runs.
"""

import shutil
from pathlib import Path

import pytest

from coding_agent.engine import CodingEngineer, _build_maker_tools, build_graph
from coding_agent.schemas import TargetSpec
from coding_agent.tools.code_exec import Jail

SAMPLE_TARGET = Path(__file__).resolve().parents[1] / "sample_target"

CORRECT_CALCULATOR = '''"""String Calculator kata -- implemented."""
import re


def add(numbers: str) -> int:
    if numbers == "":
        return 0
    parts = re.split(r"[,\\n]", numbers)
    values = [int(p) for p in parts]
    negatives = [v for v in values if v < 0]
    if negatives:
        raise ValueError("negatives not allowed: " + ",".join(str(n) for n in negatives))
    return sum(values)
'''

BROKEN_CALCULATOR = '''"""String Calculator kata -- deliberately still wrong."""


def add(numbers: str) -> int:
    return 0
'''

KATA_ACCEPTANCE_CRITERIA = [
    "add('') == 0",
    "add('1') == 1",
    "add('1,2') == 3",
    "add('1,2,3,4,5') == 15",
    "add('1\\n2,3') == 6",
    "add('1,-2,3,-4') raises an error mentioning -2 and -4",
]


@pytest.fixture
def kata_target(tmp_path, monkeypatch):
    target = tmp_path / "target"
    shutil.copytree(SAMPLE_TARGET, target)
    monkeypatch.setenv("CODING_AGENT_LOOP_DIR", str(tmp_path / ".loop"))
    return target


@pytest.fixture(autouse=True)
def _mock_phase3_llms(monkeypatch):
    """Phase 3 added an LLM call in plan_tot (propose + judge) on every run and a
    review call after every green bdd_gate. Default them to a single generic plan
    and a clean approve so the many pre-Phase-3 tests -- which only care about the
    loop mechanics -- don't each need to wire them up. Tests that specifically
    exercise ToT planning or the reviewer override these."""
    from coding_agent.schemas import (
        PlanIdea,
        PlanJudgement,
        PlanProposal,
        PlanScore,
        ReviewVerdict,
    )

    monkeypatch.setattr(
        "coding_agent.engine._llm_propose_plans",
        lambda llm, state, k: PlanProposal(plans=[PlanIdea(steps=["implement the goal"], rationale="direct")]),
    )
    monkeypatch.setattr(
        "coding_agent.engine._llm_judge_plans",
        lambda llm, state, plans: PlanJudgement(
            scores=[PlanScore(plan_index=i, score=float(len(plans) - i), reasoning="ok") for i in range(len(plans))]
        ),
    )
    monkeypatch.setattr(
        "coding_agent.engine._llm_review",
        lambda llm, state: ReviewVerdict(verdict="approve", findings=[]),
    )


def _mock_suitable_intake(monkeypatch, acceptance_criteria=KATA_ACCEPTANCE_CRITERIA):
    def fake_parse(llm, goal, target_dir):
        return TargetSpec(
            is_suitable=True,
            acceptance_criteria=list(acceptance_criteria),
            in_scope_files=["calculator.py"],
            test_command="pytest -q",
            constraints=[],
        )

    monkeypatch.setattr("coding_agent.engine._llm_parse_target_spec", fake_parse)


def _mock_unsuitable_intake(monkeypatch, reason="goal is an architecture decision, not checkable"):
    def fake_parse(llm, goal, target_dir):
        return TargetSpec(is_suitable=False, rejection_reason=reason)

    monkeypatch.setattr("coding_agent.engine._llm_parse_target_spec", fake_parse)


def _mock_maker_sequence(monkeypatch, contents: list[str]):
    """Each call to the maker writes the next `content` in the sequence
    (the last one repeats if the loop calls the maker more times than
    there are entries)."""
    calls = {"n": 0}

    def fake_run_maker(llm, jail, state):
        idx = min(calls["n"], len(contents) - 1)
        jail.write_file("calculator.py", contents[idx])
        calls["n"] += 1
        return {"output": f"attempt {calls['n']}: wrote calculator.py"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)
    return calls


def _mock_diagnose(monkeypatch, category="test-logic"):
    """Mock the diagnose LLM boundary (Phase 2) so tests that reach diagnose
    don't need a live model. The failure_signature is still computed in code
    from the real pytest/ruff failures -- only the category/insight are mocked."""
    from coding_agent.schemas import DiagnosisResult

    def fake(llm, state, phase, detail):
        return DiagnosisResult(category=category, insight=f"{phase} failed — {detail[:80]}")

    monkeypatch.setattr("coding_agent.engine._llm_diagnose", fake)


def _invoke(target: Path, goal: str, run_id: str, budgets: dict | None = None, graph=None):
    graph = graph or build_graph()
    initial_state = {
        "run_id": run_id,
        "target_dir": str(target),
        "goal": goal,
        "hitl_bdd_approval": False,
        "budgets": budgets or {},
    }
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 150}
    return graph.invoke(initial_state, config=config)


def _report_path(run_id: str) -> Path:
    import os

    return Path(os.environ["CODING_AGENT_LOOP_DIR"]) / "state" / "coding-engineer" / run_id / "run-report.md"


# -- happy path ----------------------------------------------------------


def test_pass_on_first_attempt(kata_target, monkeypatch):
    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-pass-1")

    assert final["status"] == "done"
    assert final["test_report"]["passed"] is True
    assert final["bdd_report"]["passed"] is True
    assert final["total_attempts"] == 0  # no failures -> diagnose never entered
    assert final["feature_paths"] == ["features/calculator.feature"]  # adopted, not authored

    report = _report_path("run-pass-1")
    assert report.exists()
    text = report.read_text()
    assert "Outcome:** done" in text
    assert "features/calculator.feature" in text


def test_worktree_isolated_from_target(kata_target, monkeypatch):
    """The finished implementation lives on the run's branch/worktree --
    the original target directory is never touched (CODING_ENGINEER.md §4
    Blast radius)."""
    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])

    original_stub = (kata_target / "calculator.py").read_text()
    _invoke(kata_target, "Implement the string-calculator kata.", "run-pass-2")

    assert (kata_target / "calculator.py").read_text() == original_stub
    assert not (kata_target / ".git").exists()


def test_checkpointed_graph_via_coding_engineer(kata_target, monkeypatch):
    """The CodingEngineer wrapper (SqliteSaver-backed, what app.py will call
    in Phase 4) produces the same result as the bare graph."""
    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])

    graph = CodingEngineer().create_graph()
    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-pass-3", graph=graph)

    assert final["status"] == "done"
    db_path = Path(__import__("os").environ["CODING_AGENT_LOOP_DIR"]) / "state" / "coding-engineer" / "checkpoints.db"
    assert db_path.exists()


# -- retry path ------------------------------------------------------------


def test_retry_then_pass(kata_target, monkeypatch):
    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch)
    calls = _mock_maker_sequence(monkeypatch, [BROKEN_CALCULATOR, CORRECT_CALCULATOR])

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-retry-1")

    assert final["status"] == "done"
    assert calls["n"] == 2  # maker was called twice: broken, then correct
    assert final["total_attempts"] == 1  # one failed cycle before success
    assert len(final["lessons"]) == 1
    assert "bdd_gate failed" in final["lessons"][0]["insight"]
    assert final["lessons"][0]["failure_signature"]  # Phase 2: signed

    report_text = _report_path("run-retry-1").read_text()
    assert "attempt 1 (plan-1)" in report_text
    assert "bdd_gate failed" in report_text


# -- no-progress + budget exhaustion -> escalate ---------------------------


def test_no_progress_escalates_on_identical_failure(kata_target, monkeypatch):
    """Phase 2 (§3.4 exit 1): the SAME failure signature twice in a row means
    the active plan is exhausted -- with a single plan (Phase 2) that escalates
    immediately, well before the attempt budget. A stuck maker producing the
    identical BDD failure every time is exactly the 'Ralph-Wiggum runaway' the
    no-progress detector exists to cut short."""
    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch, category="test-logic")
    calls = _mock_maker_sequence(monkeypatch, [BROKEN_CALCULATOR])  # never fixed -> identical failure

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-noprogress-1",
        budgets={"max_attempts_per_plan": 9, "max_total_attempts": 9},  # generous: prove no-progress, not budget
    )

    assert final["status"] == "escalated"
    assert final["escalation_reason"] == "no_progress"
    assert calls["n"] == 2  # first attempt + one retry, then the repeat is caught
    assert len(final["lessons"]) == 2
    sigs = [ls["failure_signature"] for ls in final["lessons"]]
    assert sigs[0] == sigs[1]  # identical signature is *why* it stopped

    report_text = _report_path("run-noprogress-1").read_text()
    assert "No-progress" in report_text


def test_exhausts_budget_when_failures_keep_changing(kata_target, monkeypatch):
    """The backstop: when each attempt fails *differently* (distinct signatures,
    so no-progress never trips) the attempt budget is what stops the run. Each
    broken implementation returns a different constant, so the first failing
    scenario's assertion message -- and thus the signature -- differs each time."""
    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch, category="test-logic")
    variants = [f"def add(numbers):\n    return {n}\n" for n in (11, 12, 13, 14)]
    calls = _mock_maker_sequence(monkeypatch, variants)

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-budget-1",
        budgets={"max_attempts_per_plan": 3, "max_total_attempts": 9},
    )

    assert final["status"] == "escalated"
    assert final["escalation_reason"] == "max_attempts_per_plan"
    assert calls["n"] == 4  # attempts 1-3 retried (distinct sigs), 4th trips the per-plan budget
    sigs = [ls["failure_signature"] for ls in final["lessons"]]
    assert len(set(sigs)) == len(sigs)  # all distinct -> no-progress never fired

    report_text = _report_path("run-budget-1").read_text()
    assert "Outcome:** escalated" in report_text
    assert "Escalation reason:**" in report_text


def test_token_budget_is_a_hard_stop(kata_target, monkeypatch):
    """Phase 4 (§3.4 exit 4): the token budget is a hard stop. The maker
    reports token usage each attempt and fails *differently* each time (distinct
    signatures, so no-progress never trips) -- once the running tally exceeds
    the budget, diagnose escalates `token_budget`."""
    from langchain_core.messages import AIMessage

    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch, category="test-logic")

    counter = {"n": 0}

    def fake_maker(llm, jail, state):
        n = counter["n"]
        counter["n"] += 1
        jail.write_file("calculator.py", f"def add(numbers):\n    return {11 + n}\n")  # distinct failure each time
        msg = AIMessage(content="done", usage_metadata={"input_tokens": 40, "output_tokens": 20, "total_tokens": 60})
        return {"output": "wrote", "messages": [msg]}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_maker)

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-tokenbudget-1",
        budgets={"max_attempts_per_plan": 9, "max_total_attempts": 9, "token_budget": 100},
    )

    assert final["status"] == "escalated"
    assert final["escalation_reason"] == "token_budget"
    assert final["tokens_used"] > 100


def test_flake_gets_a_free_retry(kata_target, monkeypatch):
    """A `flake` classification buys a retry that doesn't burn an attempt
    (§3.4). The maker fails once (classified flake), then succeeds; the free
    retry means total_attempts stays 0 even though a cycle failed."""
    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch, category="flake")
    _mock_maker_sequence(monkeypatch, [BROKEN_CALCULATOR, CORRECT_CALCULATOR])

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-flake-1")

    assert final["status"] == "done"
    assert final["total_attempts"] == 0  # the failed cycle was a free flake retry
    assert final.get("flake_free_retries") == 1
    assert "[flake" in final["lessons"][0]["insight"]


# -- suitability gate --------------------------------------------------------


def test_unsuitable_goal_escalates_without_worktree(kata_target, monkeypatch):
    _mock_unsuitable_intake(monkeypatch, reason="this is a production deployment, not checkable")

    final = _invoke(kata_target, "Deploy this to production.", "run-reject-1")

    assert final["status"] == "escalated"
    assert "unsuitable goal" in final["escalation_reason"]
    assert "worktree_dir" not in final or final.get("worktree_dir") is None

    report_text = _report_path("run-reject-1").read_text()
    assert "unsuitable goal" in report_text


# -- structured-output failure escalates gracefully (live-run fix) -----------


def test_intake_structured_failure_escalates_with_report(kata_target, monkeypatch):
    """The first live run crashed the whole graph (and surfaced a raw stack
    trace in the UI) when intake's structured output couldn't be parsed.
    Now it must escalate gracefully with a report instead."""
    from coding_agent.structured import StructuredOutputError

    def fake_parse(llm, goal, target_dir):
        raise StructuredOutputError("model answered in markdown, all retries failed")

    monkeypatch.setattr("coding_agent.engine._llm_parse_target_spec", fake_parse)

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-parsefail-1")

    assert final["status"] == "escalated"
    assert "intake structured-output failure" in final["escalation_reason"]
    report_text = _report_path("run-parsefail-1").read_text()
    assert "Outcome:** escalated" in report_text
    assert "structured-output failure" in report_text


# -- author_bdd HITL interrupt + checkpoint resume (Phase 2) -----------------

# A self-passing scenario so a resumed/clear run reaches `done` without the
# maker needing to implement anything -- the HITL tests are about the
# pause/resume mechanics, not about solving a kata.
_TRIVIAL_FEATURE = "Feature: trivial\n  Scenario: always\n    Given a thing\n    Then it holds\n"
_TRIVIAL_STEPS = (
    "from pytest_bdd import scenarios, given, then\n"
    "scenarios('../trivial.feature')\n\n"
    "@given('a thing')\n"
    "def _a():\n    pass\n\n"
    "@then('it holds')\n"
    "def _b():\n    assert True\n"
)


def _mock_author_bdd(monkeypatch, ambiguity):
    from coding_agent.schemas import BddAuthorResult

    def fake(llm, state):
        return BddAuthorResult(
            feature_gherkin=_TRIVIAL_FEATURE,
            feature_relative_path="features/trivial.feature",
            step_defs_python=_TRIVIAL_STEPS,
            step_defs_relative_path="features/steps/test_trivial.py",
            ambiguity=ambiguity,
            ambiguity_reason="two plausible readings" if ambiguity else None,
        )

    monkeypatch.setattr("coding_agent.engine._llm_author_bdd", fake)


def _mock_maker_noop(monkeypatch):
    monkeypatch.setattr("coding_agent.engine._run_maker", lambda llm, jail, state: {"output": "noop"})


def _is_paused(graph, config) -> bool:
    """With .invoke() (as opposed to .stream()), an interrupt surfaces as a
    paused checkpoint: a pending `next` node plus an interrupt on its task --
    not a '__interrupt__' key in the return value. This is how a UI would
    detect 'waiting for approval'."""
    snap = graph.get_state(config)
    return bool(snap.next) and any(task.interrupts for task in snap.tasks)


def _fresh_bdd_target(kata_target):
    """Remove the kata's adopt-existing feature so author_bdd drafts (and can
    pause), and drop its step defs so bdd_gate only runs the drafted scenario."""
    import shutil

    shutil.rmtree(kata_target / "features")
    return kata_target


def test_author_bdd_pauses_and_resumes_when_hitl_on_and_ambiguous(kata_target, monkeypatch):
    """§4 kill/approve: with the HITL flag on and an ambiguous goal, author_bdd
    pauses (langgraph interrupt) before the loop goes non-stop; resuming with an
    approval continues the run to completion."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    _mock_suitable_intake(monkeypatch)
    _mock_author_bdd(monkeypatch, ambiguity=True)
    _mock_maker_noop(monkeypatch)
    _fresh_bdd_target(kata_target)

    graph = build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "run-hitl-1"}, "recursion_limit": 150}
    initial = {
        "run_id": "run-hitl-1",
        "target_dir": str(kata_target),
        "goal": "do the ambiguous thing",
        "hitl_bdd_approval": True,
        "budgets": {},
    }

    graph.invoke(initial, config=config)
    assert _is_paused(graph, config)  # halted for human approval

    resumed = graph.invoke(Command(resume={"approved": True}), config=config)
    assert resumed["status"] == "done"
    assert resumed["feature_paths"] == ["features/trivial.feature"]


def test_author_bdd_does_not_pause_on_clear_goal_with_hitl_on(kata_target, monkeypatch):
    """The autonomy default: HITL on but the goal is unambiguous -> no pause,
    the run proceeds straight through."""
    from langgraph.checkpoint.memory import MemorySaver

    _mock_suitable_intake(monkeypatch)
    _mock_author_bdd(monkeypatch, ambiguity=False)
    _mock_maker_noop(monkeypatch)
    _fresh_bdd_target(kata_target)

    graph = build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "run-hitl-2"}, "recursion_limit": 150}
    final = graph.invoke(
        {
            "run_id": "run-hitl-2",
            "target_dir": str(kata_target),
            "goal": "do the clear thing",
            "hitl_bdd_approval": True,
            "budgets": {},
        },
        config=config,
    )
    assert not _is_paused(graph, config)
    assert final["status"] == "done"


def test_author_bdd_does_not_pause_when_hitl_off_even_if_ambiguous(kata_target, monkeypatch):
    """The flag gates the pause: HITL off means even an ambiguous goal does not
    interrupt -- the agent stays non-stop by default."""
    _mock_suitable_intake(monkeypatch)
    _mock_author_bdd(monkeypatch, ambiguity=True)
    _mock_maker_noop(monkeypatch)
    _fresh_bdd_target(kata_target)

    final = _invoke(kata_target, "do the ambiguous thing", "run-hitl-3")  # hitl defaults off
    assert "__interrupt__" not in final
    assert final["status"] == "done"


def test_killed_run_resumes_from_sqlite_checkpoint(kata_target, monkeypatch):
    """§6 durability: a run interrupted for approval is checkpointed to disk;
    a *fresh* graph instance (standing in for a restarted process) built on the
    same sqlite db + thread_id resumes it to completion."""
    import os
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    _mock_suitable_intake(monkeypatch)
    _mock_author_bdd(monkeypatch, ambiguity=True)
    _mock_maker_noop(monkeypatch)
    _fresh_bdd_target(kata_target)

    db_path = Path(os.environ["CODING_AGENT_LOOP_DIR"]) / "resume.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": "run-resume-1"}, "recursion_limit": 150}
    initial = {
        "run_id": "run-resume-1",
        "target_dir": str(kata_target),
        "goal": "do the ambiguous thing",
        "hitl_bdd_approval": True,
        "budgets": {},
    }

    # First process: run until the approval interrupt, then "die".
    conn1 = sqlite3.connect(str(db_path), check_same_thread=False)
    graph1 = build_graph(checkpointer=SqliteSaver(conn1))
    graph1.invoke(initial, config=config)
    assert _is_paused(graph1, config)
    conn1.close()

    # Second process: brand-new connection + graph over the same db resumes it.
    conn2 = sqlite3.connect(str(db_path), check_same_thread=False)
    resumed = build_graph(checkpointer=SqliteSaver(conn2)).invoke(Command(resume={"approved": True}), config=config)
    assert resumed["status"] == "done"
    conn2.close()


# -- Phase 3: ToT planning + adversarial review ------------------------------


def test_seeded_bad_plan_triggers_observable_plan_switch(kata_target, monkeypatch):
    """§3.6 ToT + GoT: with two candidate plans, a stalling plan (identical
    failure twice -> no-progress) is retired and the loop switches to the next
    plan, which succeeds. The switch is observable in state (exhausted plan,
    new active plan) and the report."""
    from coding_agent.schemas import PlanIdea, PlanProposal

    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch, category="test-logic")
    monkeypatch.setattr(
        "coding_agent.engine._llm_propose_plans",
        lambda llm, state, k: PlanProposal(
            plans=[
                PlanIdea(steps=["a doomed approach"], rationale="plan A (will stall)"),
                PlanIdea(steps=["a working approach"], rationale="plan B"),
            ]
        ),
    )

    def fake_maker(llm, jail, state):
        # plan-1 keeps producing the identical failure; plan-2 fixes it.
        content = BROKEN_CALCULATOR if state.get("active_plan_id") == "plan-1" else CORRECT_CALCULATOR
        jail.write_file("calculator.py", content)
        return {"output": f"wrote under {state.get('active_plan_id')}"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_maker)

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-planswitch-1",
        budgets={"max_attempts_per_plan": 5, "max_total_attempts": 9},
    )

    assert final["status"] == "done"
    assert "plan-1" in final.get("exhausted_plan_ids", [])
    assert final["active_plan_id"] == "plan-2"

    report_text = _report_path("run-planswitch-1").read_text()
    assert "Plans (ToT)" in report_text
    assert "exhausted" in report_text


def test_reviewer_rejects_trivial_pass_step_def(kata_target, monkeypatch):
    """§3.3 checker: the automated gates pass, but the adversarial reviewer
    rejects a blocking finding (e.g. a step def that asserts nothing) -- so the
    run does NOT finalize. The identical rejection twice is a maker/checker
    stalemate, caught by the same no-progress rule (§3.4)."""
    from coding_agent.schemas import ReviewFinding, ReviewVerdict

    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch, category="design")
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])  # gates stay green every attempt
    monkeypatch.setattr(
        "coding_agent.engine._llm_review",
        lambda llm, state: ReviewVerdict(
            verdict="reject",
            findings=[
                ReviewFinding(
                    location="features/steps/test_calculator_steps.py:add",
                    severity="blocker",
                    rationale="the step asserts nothing -- a trivial pass",
                    suggested_fix="assert the real return value",
                )
            ],
        ),
    )

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-review-1",
        budgets={"max_attempts_per_plan": 9, "max_total_attempts": 9},
    )

    assert final["status"] == "escalated"
    assert final["escalation_reason"] == "no_progress"  # same rejection twice -> stalemate
    assert final["review_result"]["verdict"] == "reject"

    report_text = _report_path("run-review-1").read_text()
    assert "review verdict: reject" in report_text
    assert "asserts nothing" in report_text


def test_judge_and_review_use_secondary_role(kata_target, monkeypatch):
    """§3.5: the plan judge and the reviewer must run on the `secondary` role,
    while proposing/coding stay on `primary` -- so a distinct
    CODING_AGENT_SECONDARY_MODEL is actually exercised as the checker."""
    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])

    roles: list[str] = []
    monkeypatch.setattr("coding_agent.engine.get_llm", lambda role, **kw: roles.append(role) or object())

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-roles-1")

    assert final["status"] == "done"
    assert "secondary" in roles  # judge + review
    assert "primary" in roles  # intake + propose + code
    # the two secondary calls are the judge (plan_tot) and the reviewer.
    assert roles.count("secondary") >= 2


# -- tool arg-schema collisions (live-run fix) -------------------------------


def test_maker_tools_have_no_reserved_field_collisions(tmp_path):
    """Regression test for the second live-run failure: a tool parameter
    literally named `args` (run_pytest's original signature) collides with
    pydantic's function-wrapping internals, which silently rename it to
    `v__args` AND change its type from string to array in the generated
    schema -- so a tool-calling model passing a plain string for it always
    fails with 'unexpected keyword argument'. Checks every maker tool's
    *actual* invocation schema (not just the underlying Python function)
    for the reserved names, and proves each tool is actually callable the
    way a tool-calling agent would call it -- via a dict of named args,
    not a direct Python call."""
    root = tmp_path / "worktree"
    root.mkdir()
    jail = Jail(root=root)
    tools = _build_maker_tools(jail, {"cmd_timeout_s": 5})

    reserved = {"v__args", "v__kwargs", "v__positional_only", "args", "kwargs"}
    for t in tools:
        schema_fields = set(t.args.keys())
        assert not (schema_fields & reserved), f"{t.name} has a reserved field name collision: {schema_fields}"

    run_pytest_tool = next(t for t in tools if t.name == "run_pytest")
    assert run_pytest_tool.args["pytest_args"]["type"] == "string"
    result = run_pytest_tool.invoke({"pytest_args": "--collect-only"})
    assert "returncode=" in result


# -- stop flag ---------------------------------------------------------------


def test_stop_flag_halts_at_next_diagnose(kata_target, monkeypatch):
    """CODING_ENGINEER.md §4 Kill switch: a STOP file is checked at diagnose
    entry, so a run in the middle of a retry loop halts within one attempt
    rather than continuing to burn the budget."""
    import os

    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [BROKEN_CALCULATOR, CORRECT_CALCULATOR])

    run_id = "run-stop-1"
    loop_dir = Path(os.environ["CODING_AGENT_LOOP_DIR"])
    stop_path = loop_dir / "state" / "coding-engineer" / run_id / "STOP"
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_text("stop")

    final = _invoke(kata_target, "Implement the string-calculator kata.", run_id)

    assert final["status"] == "escalated"
    assert final["escalation_reason"] == "stopped by user"


# -- maker tool surface: delete_file / move_file (Phase 1 follow-up) --------


def test_maker_tools_include_delete_and_move(tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    (root / "features").mkdir()
    (root / "features" / "x.feature").write_text("Feature: stub\n")
    jail = Jail(root=root, frozen=frozenset({Path("features/x.feature")}))
    tools = _build_maker_tools(jail, {"cmd_timeout_s": 5})
    names = {t.name for t in tools}

    assert {"read_file", "list_dir", "write_file", "delete_file", "move_file", "run_pytest"} <= names

    jail.write_file("scratch.txt", "hello")
    delete_tool = next(t for t in tools if t.name == "delete_file")
    move_tool = next(t for t in tools if t.name == "move_file")

    jail.write_file("a.txt", "content")
    result = move_tool.invoke({"src_path": "a.txt", "dst_path": "b.txt"})
    assert "moved" in result
    assert (root / "b.txt").read_text() == "content"
    assert not (root / "a.txt").exists()

    result = delete_tool.invoke({"path": "scratch.txt"})
    assert "deleted" in result
    assert not (root / "scratch.txt").exists()

    # frozen feature file: both tools refuse, and say so instead of
    # silently doing nothing (CODING_ENGINEER.md §4 Filesystem jail).
    result = delete_tool.invoke({"path": "features/x.feature"})
    assert result.startswith("ERROR")
    assert "frozen" in result


def test_maker_can_move_a_module_and_fix_the_import(kata_target, monkeypatch):
    """The shape of the RAG-chatbot refactor POC: relocate a module into a
    subfolder, update the one file that imports it, delete the original.
    Proves delete_file/move_file are actually wired end-to-end through the
    graph, not just unit-testable in isolation."""
    _mock_suitable_intake(monkeypatch, acceptance_criteria=["calculator.py lives under sub/ and all scenarios still pass"])

    def fake_run_maker(llm, jail, state):
        jail.write_file("sub/calculator.py", CORRECT_CALCULATOR)
        # Step defs aren't frozen (only the .feature file is -- see
        # CODING_ENGINEER.md §3.3/§4), so fixing the import here is exactly
        # the sanctioned "glue code" edit the maker is expected to make.
        steps_path = "features/steps/test_calculator_steps.py"
        original_steps = jail.read_file(steps_path)
        fixed_steps = original_steps.replace(
            'sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\nfrom calculator import add',
            'sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sub"))\nfrom calculator import add',
        )
        assert fixed_steps != original_steps, "test fixture drifted from the replace() target"
        jail.write_file(steps_path, fixed_steps)
        jail.delete_file("calculator.py")
        return {"output": "moved calculator.py to sub/, fixed the step-defs import"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)

    final = _invoke(kata_target, "Move calculator.py into a sub/ subfolder.", "run-move-1")

    assert final["status"] == "done"
    assert final["bdd_report"]["passed"] is True
    assert "--- a/calculator.py" in final["last_diff"]  # old file removed
    assert "+++ b/sub/calculator.py" in final["last_diff"]  # new file added


# -- self_check / bdd_gate scope: never recurse into the agent's own harness --


def test_self_check_excludes_nested_coding_agent_dir(kata_target, monkeypatch):
    """If the target repo happens to contain a coding_agent/ directory (i.e.
    someone points the agent at its own repo -- the self-hosting case this
    fix was written for), self_check/bdd_gate must not run its ~40-test
    suite as a side effect of an unrelated goal."""
    nested = kata_target / "coding_agent" / "tests"
    nested.mkdir(parents=True)
    (nested / "test_always_fails.py").write_text("def test_boom():\n    assert False\n")

    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-exclude-1")

    assert final["status"] == "done"
    assert final["test_report"]["passed"] is True


def test_author_bdd_excludes_nested_coding_agent_dir(kata_target, monkeypatch):
    """Same self-hosting scenario, but for author_bdd's "adopt existing
    .feature file" scan specifically: this is the more serious of the two
    bugs found on the first real self-hosted run, since an unscoped rglob
    silently froze coding_agent/sample_target/features/calculator.feature --
    the agent's own demo fixture -- as the definition of done for a
    completely unrelated goal. The nested copy must be ignored in favour of
    the target's real, top-level feature file."""
    nested_features = kata_target / "coding_agent" / "sample_target" / "features"
    nested_features.mkdir(parents=True)
    (nested_features / "calculator.feature").write_text(
        "Feature: decoy\n  Scenario: should never be adopted\n    Given nothing\n"
    )

    _mock_suitable_intake(monkeypatch)
    _mock_maker_sequence(monkeypatch, [CORRECT_CALCULATOR])

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-author-bdd-exclude-1")

    assert final["status"] == "done"
    assert final["feature_paths"] == ["features/calculator.feature"]
    assert not any("coding_agent" in p for p in final["feature_paths"])


# -- self_check ruff: forgive pre-existing debt, catch newly-introduced --


def test_self_check_forgives_preexisting_lint_debt(kata_target, monkeypatch):
    """The exact bug that escalated the first real POC run 4x: self_check must
    not fail on lint debt that already existed in a file the maker legitimately
    had to touch. helper.py ships with a duplicate `import os` (F811/F401); the
    maker implements the kata AND appends a line to helper.py (as it would when,
    e.g., updating an import). The pre-existing findings are forgiven because
    they're present at the baseline too; BDD passes; the run finishes done."""
    (kata_target / "helper.py").write_text(
        "import os\nimport os\n\n\ndef helper():\n    return 1\n"
    )

    _mock_suitable_intake(monkeypatch)

    def fake_run_maker(llm, jail, state):
        jail.write_file("calculator.py", CORRECT_CALCULATOR)
        jail.write_file("helper.py", jail.read_file("helper.py") + "\n# touched by maker\n")
        return {"output": "implemented kata; also touched helper.py"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-forgive-1")

    assert final["status"] == "done"
    assert final["test_report"]["passed"] is True


def test_self_check_forgives_lint_debt_in_a_moved_file(kata_target, monkeypatch):
    """A moved file has no blob at its NEW path in HEAD, so without
    rename-aware baseline lookup every finding in it reads as 'introduced
    this run'. This was the actual escalation cause on the RAG POC:
    rag_research_chatbot.py carried pre-existing pyflakes debt, and relocating
    it into rag_agent/ made that debt fail self_check at the new path. Here
    legacy.py ships with an unused import; the maker implements the kata and
    relocates legacy.py verbatim into pkg/ -- the moved file's pre-existing
    F401 must be forgiven via git rename detection."""
    (kata_target / "legacy.py").write_text(
        "import os  # unused, pre-existing\n\n\ndef legacy():\n    return 1\n"
    )

    _mock_suitable_intake(monkeypatch)

    def fake_run_maker(llm, jail, state):
        jail.write_file("calculator.py", CORRECT_CALCULATOR)
        jail.write_file("pkg/legacy.py", jail.read_file("legacy.py"))  # verbatim relocate
        jail.delete_file("legacy.py")
        return {"output": "implemented kata; relocated legacy.py into pkg/"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-moved-debt-1")

    assert final["status"] == "done"
    assert final["test_report"]["passed"] is True


def test_self_check_ignores_lint_in_bdd_harness(kata_target, monkeypatch):
    """self_check must not lint the frozen BDD harness (the feature dir and its
    step defs) -- that's author_bdd-generated code that bdd_gate runs, not the
    maker's implementation change. author_bdd routinely leaves an unused
    `import pytest` (F401) in the step-defs file it writes; the live RAG POC
    actually completed the move and then escalated *solely* because self_check
    flagged that F401. Here a new .py under features/ carries an unused import;
    the run must still finish done."""
    _mock_suitable_intake(monkeypatch)

    def fake_run_maker(llm, jail, state):
        jail.write_file("calculator.py", CORRECT_CALCULATOR)
        jail.write_file("features/steps/extra_helper.py", "import pytest\n")  # unused -> F401
        return {"output": "implemented kata; added a helper under features/"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-bdd-lint-1")

    assert final["status"] == "done"
    assert final["test_report"]["passed"] is True


def test_self_check_allows_reexport_init_py(kata_target, monkeypatch):
    """A brand-new package __init__.py that re-exports a name trips F401
    ('imported but unused') even though re-exporting is its entire purpose,
    and being new it has no baseline to forgive it against. self_check must
    tolerate F401 in __init__.py specifically -- this is exactly what the RAG
    POC does (rag_agent/__init__.py re-exporting RAGResearchChatbot). The
    maker here creates pkg/thing.py and a re-exporting pkg/__init__.py while
    implementing the kata."""
    _mock_suitable_intake(monkeypatch)

    def fake_run_maker(llm, jail, state):
        jail.write_file("calculator.py", CORRECT_CALCULATOR)
        jail.write_file("pkg/thing.py", "class Thing:\n    pass\n")
        jail.write_file("pkg/__init__.py", "from pkg.thing import Thing\n")  # F401 by default
        return {"output": "implemented kata; added a re-exporting pkg/__init__.py"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-reexport-1")

    assert final["status"] == "done"
    assert final["test_report"]["passed"] is True


def test_self_check_fails_on_newly_introduced_finding(kata_target, monkeypatch):
    """The flip side: a finding the maker *introduces* still fails self_check.
    The maker writes a working calculator but with an unused `import sys` (F401)
    that wasn't in the baseline stub -- correct behaviour, new lint debt. It
    keeps writing the same file, so the run escalates, proving the gate blocks
    on the introduced finding rather than letting it through."""
    _mock_suitable_intake(monkeypatch)
    _mock_diagnose(monkeypatch)
    dirty_calc = "import sys\n" + CORRECT_CALCULATOR  # unused import -> F401, not in baseline

    def fake_run_maker(llm, jail, state):
        jail.write_file("calculator.py", dirty_calc)
        return {"output": "implemented kata (with an unused import)"}

    monkeypatch.setattr("coding_agent.engine._run_maker", fake_run_maker)

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-newfinding-1",
        budgets={"max_attempts_per_plan": 2, "max_total_attempts": 2},
    )

    assert final["status"] == "escalated"
    assert final["test_report"]["passed"] is False
    assert "F401" in (final["test_report"]["ruff"]["stdout"] or "")
