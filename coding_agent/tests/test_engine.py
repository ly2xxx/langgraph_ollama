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

from coding_agent.engine import CodingEngineer, build_graph
from coding_agent.schemas import TargetSpec

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
