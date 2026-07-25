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
    calls = _mock_maker_sequence(monkeypatch, [BROKEN_CALCULATOR, CORRECT_CALCULATOR])

    final = _invoke(kata_target, "Implement the string-calculator kata.", "run-retry-1")

    assert final["status"] == "done"
    assert calls["n"] == 2  # maker was called twice: broken, then correct
    assert final["total_attempts"] == 1  # one failed cycle before success
    assert len(final["lessons"]) == 1
    assert "bdd_gate failed" in final["lessons"][0]["insight"]

    report_text = _report_path("run-retry-1").read_text()
    assert "attempt 1 (plan-1): bdd_gate failed" in report_text


# -- budget exhaustion -> escalate -----------------------------------------


def test_exhausts_budget_and_escalates(kata_target, monkeypatch):
    _mock_suitable_intake(monkeypatch)
    calls = _mock_maker_sequence(monkeypatch, [BROKEN_CALCULATOR])  # never fixed

    final = _invoke(
        kata_target,
        "Implement the string-calculator kata.",
        "run-escalate-1",
        budgets={"max_attempts_per_plan": 2, "max_total_attempts": 2},
    )

    assert final["status"] == "escalated"
    assert final["escalation_reason"] in ("max_attempts_per_plan", "max_total_attempts")
    assert calls["n"] == 3  # initial attempt + 2 retries before the budget check trips
    assert len(final["lessons"]) == 3  # diagnose is entered once per failed attempt

    report_text = _report_path("run-escalate-1").read_text()
    assert "Outcome:** escalated" in report_text
    assert "Escalation reason:**" in report_text


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
