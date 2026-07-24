"""Coding Engineer — the non-stop coding agent's LangGraph graph.

Phase 1 scope (CODING_ENGINEER.md §6): the linear loop —
intake -> author_bdd -> plan_tot (single fixed plan) -> code -> self_check
-> bdd_gate -> finalize, with a diagnose stub that retries on failure up to
a budget, then escalates. No plan-switching (ToT/GoT, Phase 3), no
signature-based no-progress detection (Phase 2), no adversarial reviewer
(Phase 3) yet — see PHASED_PLAN.md for exactly what each phase added.

Every LLM call goes through a small boundary function (`_llm_parse_target_spec`,
`_llm_author_bdd`, `_run_maker`) so tests can monkeypatch just the model call
and exercise the real graph, worktree, gates, and report writer around it.

Phase 1 follow-up (see PHASED_PLAN.md): the maker's tool surface now
includes delete_file/move_file (not just write_file), and self_check/bdd_gate
exclude coding_agent/ from their own scope when present in the target --
both added once a real refactor-shaped goal (relocating a module to a
subfolder within this repo) showed the Phase 1-as-shipped surface wasn't
quite enough for that shape of task.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from coding_agent.models import get_llm
from coding_agent.prompts import AUTHOR_BDD_PROMPT, INTAKE_PROMPT, MAKER_SYSTEM_PROMPT
from coding_agent.report import stop_flag_set, write_run_report
from coding_agent.schemas import BddAuthorResult, TargetSpec
from coding_agent.tools.code_exec import Jail, JailViolation, run_command
from coding_agent.tools.worktree import WorktreeHandle, create_worktree
from coding_agent.tools.worktree import commit as worktree_commit
from coding_agent.tools.worktree import diff as worktree_diff

DEFAULT_BUDGETS: dict[str, int] = {
    "max_attempts_per_plan": 3,
    "max_plans": 3,
    "max_total_attempts": 9,
    "cmd_timeout_s": 120,
    "wall_clock_s": 1800,
    "token_budget": 0,
}


# ---------------------------------------------------------------------------
# State schema (CODING_ENGINEER.md §3.2)
#
# Three fields were added during Phase 1 implementation that the original
# plan didn't spell out a home for; see PHASED_PLAN.md "Deviations":
#   - escalation_reason: escalate's reason needs to travel through state.
#   - run_started_at: wall-clock budget needs a start time to compare against.
#   - is_fallback_copy: finalize/escalate need to reconstruct a WorktreeHandle
#     to commit/diff, and that dataclass field has to come from somewhere.
# ---------------------------------------------------------------------------


class Budgets(TypedDict):
    max_attempts_per_plan: int
    max_plans: int
    max_total_attempts: int
    cmd_timeout_s: int
    wall_clock_s: int
    token_budget: int


class Plan(TypedDict):
    id: str
    steps: list[str]
    rationale: str
    score: float
    status: str


class Lesson(TypedDict):
    attempt: int
    plan_id: str
    failure_signature: str | None
    insight: str


class CodingLoopState(TypedDict, total=False):
    # immutable per run
    run_id: str
    target_dir: str
    worktree_dir: str
    branch: str
    is_fallback_copy: bool  # added in Phase 1 -- see module docstring
    goal: str
    budgets: Budgets
    # goal definition
    spec: dict
    feature_paths: list[str]
    hitl_bdd_approval: bool
    # planning
    candidate_plans: list[Plan]
    active_plan_id: str
    lessons: list[Lesson]
    # iteration
    attempt: int
    total_attempts: int
    run_started_at: float  # added in Phase 1 -- see module docstring
    last_diff: str
    test_report: dict
    bdd_report: dict
    review: dict | None
    escalation_reason: str | None  # added in Phase 1 -- see module docstring
    # outcome + UI
    status: str
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _loop_state_dir() -> Path:
    return Path(os.getenv("CODING_AGENT_LOOP_DIR", ".loop"))


def _status_message(node: str, ok: bool, note: str = "") -> AIMessage:
    tag = "OK" if ok else "FAIL"
    content = f"[{node}] {tag}" + (f" — {note}" if note else "")
    return AIMessage(content=content, name=node)


def _handle_from_state(state: CodingLoopState) -> WorktreeHandle:
    return WorktreeHandle(
        target_dir=Path(state["target_dir"]),
        worktree_dir=Path(state["worktree_dir"]),
        branch=state["branch"],
        is_fallback_copy=state.get("is_fallback_copy", False),
    )


def _read_json_report(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("summary", {})


def _summarize_failure(state: CodingLoopState) -> str:
    """Pure-code, no-LLM failure summary for the Phase 1 lesson log.

    Phase 2 (CODING_ENGINEER.md §3.4) replaces this with an LLM-classified,
    normalised failure_signature; this stub keeps the state shape (lessons
    with an `insight` string) stable across that upgrade.
    """
    test_report = state.get("test_report") or {}
    bdd_report = state.get("bdd_report") or {}
    if not test_report.get("passed", True):
        return (
            f"self_check failed — ruff rc={test_report.get('ruff', {}).get('returncode')}, "
            f"pytest rc={test_report.get('pytest', {}).get('returncode')}, "
            f"summary={test_report.get('pytest', {}).get('summary')}"
        )
    if not bdd_report.get("passed", True):
        return f"bdd_gate failed — pytest rc={bdd_report.get('returncode')}, summary={bdd_report.get('summary')}"
    return "unknown failure (neither self_check nor bdd_report marked failed)"


# ---------------------------------------------------------------------------
# LLM call boundaries -- monkeypatch these in tests to avoid needing a live model
# ---------------------------------------------------------------------------


def _llm_parse_target_spec(llm, goal: str, target_dir: str) -> TargetSpec:
    structured = llm.with_structured_output(TargetSpec)
    prompt = INTAKE_PROMPT.format(goal=goal, target_dir=target_dir)
    return structured.invoke(prompt)


def _llm_author_bdd(llm, state: CodingLoopState) -> BddAuthorResult:
    structured = llm.with_structured_output(BddAuthorResult)
    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
    prompt = AUTHOR_BDD_PROMPT.format(
        goal=state["goal"],
        acceptance_criteria="\n".join(f"- {c}" for c in criteria) or "(none extracted)",
    )
    return structured.invoke(prompt)


def _build_maker_tools(jail: Jail, budgets: Budgets) -> list:
    """Read/list/write/delete/move plus a scoped pytest runner. `run_command`
    supports more binaries than are exposed here (e.g. `git`, `ruff`) --
    self_check/bdd_gate already cover those; the maker doesn't need them
    directly. delete_file/move_file were added after Phase 1 shipped (see
    PHASED_PLAN.md "Phase 1 follow-up") once a real refactor-shaped goal
    (moving a module to a subfolder) showed write-only wasn't enough for a
    clean move -- the old path would just be left behind as a duplicate."""

    @tool
    def read_file(path: str) -> str:
        """Read a text file's contents. `path` is relative to the worktree root."""
        try:
            return jail.read_file(path)
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def list_dir(path: str = ".") -> str:
        """List a directory's entries. `path` is relative to the worktree root."""
        try:
            return "\n".join(jail.list_dir(path))
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Write (create or overwrite) a text file with the given full content.
        `path` is relative to the worktree root. Refuses frozen BDD feature files."""
        try:
            jail.write_file(path, content)
            return f"wrote {path}"
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def delete_file(path: str) -> str:
        """Delete a file. `path` is relative to the worktree root. Refuses
        frozen BDD feature files. Use this to remove a file after moving its
        content elsewhere with write_file -- write_file alone never deletes
        the original."""
        try:
            jail.delete_file(path)
            return f"deleted {path}"
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def move_file(src_path: str, dst_path: str) -> str:
        """Move/rename a file. Both paths are relative to the worktree root.
        Refuses the operation if either end is a frozen BDD feature file."""
        try:
            jail.move_file(src_path, dst_path)
            return f"moved {src_path} -> {dst_path}"
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def run_pytest(args: str = "") -> str:
        """Run pytest inside the worktree to check your work before finishing.
        `args` is an optional space-separated string of extra pytest arguments."""
        extra = args.split() if args else []
        result = run_command("pytest", ["-q", *extra], cwd=jail.root, timeout_s=budgets["cmd_timeout_s"])
        return f"returncode={result.returncode}\n{result.stdout}\n{result.stderr}"

    return [read_file, list_dir, write_file, delete_file, move_file, run_pytest]


def _maker_task_text(state: CodingLoopState) -> str:
    spec = state.get("spec") or {}
    lessons = state.get("lessons") or []
    lesson_lines = "\n".join(f"- {lesson['insight']}" for lesson in lessons[-3:]) or "(none yet)"
    criteria = "\n".join(f"- {c}" for c in spec.get("acceptance_criteria", [])) or "(none extracted)"
    return (
        f"Goal: {state['goal']}\n\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        f"Frozen BDD scenarios (do not edit): {', '.join(state.get('feature_paths', [])) or '(none)'}\n\n"
        f"Recent lessons from earlier attempts:\n{lesson_lines}\n\n"
        "Make the smallest change that could make the tests pass. You may read files, "
        "list directories, write files, delete files, move/rename files, and run pytest "
        "to check your work. If you move something, delete the original -- write_file "
        "alone does not remove it."
    )


def _run_maker(llm, jail: Jail, state: CodingLoopState) -> dict[str, Any]:
    tools = _build_maker_tools(jail, state["budgets"])
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", MAKER_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=8)
    task_message = HumanMessage(content=_maker_task_text(state))
    return executor.invoke({"messages": [task_message]})


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def intake_node(state: CodingLoopState) -> dict:
    budgets = {**DEFAULT_BUDGETS, **(state.get("budgets") or {})}
    llm = get_llm("primary")
    spec = _llm_parse_target_spec(llm, state["goal"], state["target_dir"])

    if not spec.is_suitable:
        return {
            "spec": spec.model_dump(),
            "budgets": budgets,
            "run_started_at": time.time(),
            "status": "escalated",
            "escalation_reason": f"unsuitable goal: {spec.rejection_reason or 'not checkable'}",
            "messages": [_status_message("intake", False, note=spec.rejection_reason or "goal rejected")],
        }

    handle = create_worktree(Path(state["target_dir"]), state["run_id"], _loop_state_dir())

    return {
        "spec": spec.model_dump(),
        "budgets": budgets,
        "worktree_dir": str(handle.worktree_dir),
        "branch": handle.branch,
        "target_dir": str(handle.target_dir),
        "is_fallback_copy": handle.is_fallback_copy,
        "run_started_at": time.time(),
        "attempt": 0,
        "total_attempts": 0,
        "lessons": [],
        "candidate_plans": [],
        "feature_paths": [],
        "status": "planning",
        "messages": [_status_message("intake", True, note=f"worktree ready at {handle.worktree_dir}")],
    }


def _route_after_intake(state: CodingLoopState) -> str:
    return "escalate" if state.get("status") == "escalated" else "author_bdd"


def author_bdd_node(state: CodingLoopState) -> dict:
    worktree_dir = Path(state["worktree_dir"])
    existing = sorted(
        str(p.relative_to(worktree_dir)).replace(os.sep, "/")
        for p in worktree_dir.rglob("*.feature")
        if ".git" not in p.parts
    )

    if existing:
        return {
            "feature_paths": existing,
            "status": "planning",
            "messages": [
                _status_message("author_bdd", True, note=f"adopted existing: {', '.join(existing)}")
            ],
        }

    llm = get_llm("primary", temperature=0.3)
    result = _llm_author_bdd(llm, state)

    if state.get("hitl_bdd_approval") and result.ambiguity:
        payload = interrupt(
            {
                "node": "author_bdd",
                "reason": result.ambiguity_reason,
                "draft_feature_gherkin": result.feature_gherkin,
                "draft_feature_relative_path": result.feature_relative_path,
            }
        )
        if isinstance(payload, dict):
            result.feature_gherkin = payload.get("feature_gherkin", result.feature_gherkin)
            result.feature_relative_path = payload.get("feature_relative_path", result.feature_relative_path)

    jail = Jail(root=worktree_dir)  # nothing frozen yet -- these are the files being authored
    jail.write_file(result.feature_relative_path, result.feature_gherkin)
    jail.write_file(result.step_defs_relative_path, result.step_defs_python)

    return {
        "feature_paths": [result.feature_relative_path],
        "status": "planning",
        "messages": [_status_message("author_bdd", True, note=f"drafted {result.feature_relative_path}")],
    }


def plan_tot_node(state: CodingLoopState) -> dict:
    """Phase 1: a single fixed plan, no LLM call. ToT propose/judge/select
    and GoT lesson aggregation across plans are Phase 3 (CODING_ENGINEER.md §3.6)."""
    plan: Plan = {
        "id": "plan-1",
        "steps": ["Implement the goal against the acceptance criteria; iterate using self_check/bdd_gate feedback."],
        "rationale": "Phase 1 uses a single fixed plan -- see CODING_ENGINEER.md §3.6 for the Phase 3 upgrade.",
        "score": 1.0,
        "status": "active",
    }
    return {"candidate_plans": [plan], "active_plan_id": plan["id"], "status": "coding"}


def code_node(state: CodingLoopState) -> dict:
    jail = Jail(root=Path(state["worktree_dir"]), frozen=frozenset(Path(p) for p in state.get("feature_paths", [])))
    llm = get_llm("primary", temperature=0.2)
    maker_result = _run_maker(llm, jail, state)

    handle = _handle_from_state(state)
    diff_text = worktree_diff(handle)

    summary = maker_result.get("output", "") if isinstance(maker_result, dict) else str(maker_result)
    return {
        "last_diff": diff_text,
        "status": "coding",
        "messages": [_status_message("code", True, note=str(summary)[:200])],
    }


def _harness_exclude_dirs(worktree_dir: Path) -> list[str]:
    """Directories self_check/bdd_gate should never recurse into, regardless
    of the target's own scope: the agent's own package, when the target
    happens to be (or contain) this repo -- e.g. when self-hosting the
    Coding Engineer on its own codebase, a goal about some other file has
    no business running coding_agent's ~40-test suite as a side effect.
    Only returned if actually present, so this is a no-op for any other
    target. Added after Phase 1 shipped -- see PHASED_PLAN.md "Phase 1
    follow-up"."""
    return ["coding_agent"] if (worktree_dir / "coding_agent").is_dir() else []


def self_check_node(state: CodingLoopState) -> dict:
    worktree_dir = Path(state["worktree_dir"])
    timeout = state["budgets"]["cmd_timeout_s"]
    harness_excludes = _harness_exclude_dirs(worktree_dir)

    # `--select E9,F` (pyflakes + syntax errors) rather than bare `ruff check .`:
    # self_check runs against an arbitrary target worktree whose own ruff
    # config (if any) we don't control and shouldn't depend on -- ruff's
    # config auto-discovery can pick up unrelated rule sets (or, on some
    # filesystems, flag things like EXE002 off the executable bit that have
    # nothing to do with code correctness). An explicit, minimal, always-the-same
    # selection keeps this gate a fast correctness check, not a style audit.
    ruff_result = run_command(
        "ruff",
        ["check", ".", "--select", "E9,F", *[f"--extend-exclude={d}" for d in harness_excludes]],
        cwd=worktree_dir,
        timeout_s=timeout,
    )

    ignore_args: list[str] = []
    for feature_path in state.get("feature_paths", []):
        ignore_args.extend(["--ignore", str(Path(feature_path).parent)])
    for excluded in harness_excludes:
        ignore_args.extend(["--ignore", excluded])

    report_file = worktree_dir / ".self_check_report.json"
    pytest_result = run_command(
        "pytest",
        ["-q", *ignore_args, "--json-report", f"--json-report-file={report_file.name}"],
        cwd=worktree_dir,
        timeout_s=timeout,
    )
    summary = _read_json_report(report_file)
    report_file.unlink(missing_ok=True)

    # pytest exits 5 when it collects zero tests -- expected when the only
    # tests in scope ARE the frozen BDD scenarios (self_check ignores them;
    # bdd_gate is the node responsible for actually finding and running them).
    pytest_ok = pytest_result.returncode in (0, 5) and not pytest_result.timed_out
    passed = ruff_result.returncode == 0 and not ruff_result.timed_out and pytest_ok

    test_report = {
        "ruff": {
            "returncode": ruff_result.returncode,
            "stdout": ruff_result.stdout,
            "stderr": ruff_result.stderr,
            "timed_out": ruff_result.timed_out,
        },
        "pytest": {
            "returncode": pytest_result.returncode,
            "stdout": pytest_result.stdout,
            "stderr": pytest_result.stderr,
            "timed_out": pytest_result.timed_out,
            "summary": summary,
        },
        "passed": passed,
    }
    return {"test_report": test_report, "status": "testing", "messages": [_status_message("self_check", passed)]}


def _route_after_self_check(state: CodingLoopState) -> str:
    return "bdd_gate" if state["test_report"]["passed"] else "diagnose"


def bdd_gate_node(state: CodingLoopState) -> dict:
    worktree_dir = Path(state["worktree_dir"])
    timeout = state["budgets"]["cmd_timeout_s"]
    feature_paths = state.get("feature_paths", [])
    scope_dirs = sorted({str(Path(p).parent) for p in feature_paths}) or ["."]
    # Defensive, not just belt-and-braces for the common case: scope_dirs
    # only falls back to "." if feature_paths is somehow empty here, but
    # when it does, this is what stops that fallback from recursing into
    # the agent's own harness -- see _harness_exclude_dirs.
    ignore_args = [arg for excluded in _harness_exclude_dirs(worktree_dir) for arg in ("--ignore", excluded)]

    report_file = worktree_dir / ".bdd_report.json"
    result = run_command(
        "pytest",
        ["-q", *scope_dirs, *ignore_args, "--json-report", f"--json-report-file={report_file.name}"],
        cwd=worktree_dir,
        timeout_s=timeout,
    )
    summary = _read_json_report(report_file)
    report_file.unlink(missing_ok=True)

    passed = result.returncode == 0 and not result.timed_out
    bdd_report = {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "summary": summary,
        "passed": passed,
    }
    return {"bdd_report": bdd_report, "status": "testing", "messages": [_status_message("bdd_gate", passed)]}


def _route_after_bdd_gate(state: CodingLoopState) -> str:
    return "finalize" if state["bdd_report"]["passed"] else "diagnose"


def diagnose_node(state: CodingLoopState) -> dict:
    """Phase 1 stub: attempt/budget counting and a plain-text failure summary
    only. Signature-based no-progress detection, plan-exhaustion, and the
    two-consecutive-exhausted-plans hard exit are Phase 2 (CODING_ENGINEER.md §3.4)."""
    if stop_flag_set(state["run_id"], _loop_state_dir()):
        return {"status": "escalated", "escalation_reason": "stopped by user"}

    budgets = state["budgets"]
    elapsed = time.time() - state.get("run_started_at", time.time())
    attempt = state.get("attempt", 0) + 1
    total_attempts = state.get("total_attempts", 0) + 1

    lessons = list(state.get("lessons", []))
    lessons.append(
        {
            "attempt": attempt,
            "plan_id": state.get("active_plan_id", "plan-1"),
            "failure_signature": None,  # Phase 2 -- CODING_ENGINEER.md §3.4
            "insight": _summarize_failure(state),
        }
    )

    if elapsed > budgets["wall_clock_s"]:
        reason = "wall_clock"
    elif total_attempts > budgets["max_total_attempts"]:
        reason = "max_total_attempts"
    elif attempt > budgets["max_attempts_per_plan"]:
        reason = "max_attempts_per_plan"
    else:
        reason = None

    if reason:
        return {
            "status": "escalated",
            "escalation_reason": reason,
            "attempt": attempt,
            "total_attempts": total_attempts,
            "lessons": lessons,
        }

    return {"status": "coding", "attempt": attempt, "total_attempts": total_attempts, "lessons": lessons}


def _route_after_diagnose(state: CodingLoopState) -> str:
    return "escalate" if state.get("status") == "escalated" else "code"


def finalize_node(state: CodingLoopState) -> dict:
    handle = _handle_from_state(state)
    rev = worktree_commit(handle, f"coding-engineer: {state['goal'][:72]}")
    report_path = write_run_report(state, _loop_state_dir(), outcome="done", commit_rev=rev)
    return {"status": "done", "messages": [_status_message("finalize", True, note=f"report: {report_path}")]}


def escalate_node(state: CodingLoopState) -> dict:
    reason = state.get("escalation_reason") or "unknown"
    rev = ""
    if state.get("worktree_dir"):
        handle = _handle_from_state(state)
        rev = worktree_commit(handle, f"coding-engineer: WIP, escalated ({reason})")
    report_path = write_run_report(state, _loop_state_dir(), outcome="escalated", commit_rev=rev)
    return {"status": "escalated", "messages": [_status_message("escalate", False, note=f"{reason}; report: {report_path}")]}


# ---------------------------------------------------------------------------
# graph assembly
# ---------------------------------------------------------------------------


def build_graph(checkpointer=None):
    graph = StateGraph(CodingLoopState)
    graph.add_node("intake", intake_node)
    graph.add_node("author_bdd", author_bdd_node)
    graph.add_node("plan_tot", plan_tot_node)
    graph.add_node("code", code_node)
    graph.add_node("self_check", self_check_node)
    graph.add_node("bdd_gate", bdd_gate_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", _route_after_intake, {"author_bdd": "author_bdd", "escalate": "escalate"})
    graph.add_edge("author_bdd", "plan_tot")
    graph.add_edge("plan_tot", "code")
    graph.add_edge("code", "self_check")
    graph.add_conditional_edges("self_check", _route_after_self_check, {"bdd_gate": "bdd_gate", "diagnose": "diagnose"})
    graph.add_conditional_edges("bdd_gate", _route_after_bdd_gate, {"finalize": "finalize", "diagnose": "diagnose"})
    graph.add_conditional_edges("diagnose", _route_after_diagnose, {"code": "code", "escalate": "escalate"})
    graph.add_edge("finalize", END)
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer)


class CodingEngineer:
    """Matches the file-layout plan (CODING_ENGINEER.md §5): `CodingEngineer().create_graph()`
    is what app.py calls in Phase 4. Owns the SqliteSaver checkpointer lifecycle."""

    def create_graph(self):
        loop_dir = _loop_state_dir()
        db_path = loop_dir / "state" / "coding-engineer" / "checkpoints.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        return build_graph(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def new_run_id() -> str:
    # Local time is fine here -- this is a human-readable, sortable id
    # component, not a timezone-sensitive value used in any comparison.
    return f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"  # noqa: DTZ005


def stream_run(run_id: str, target_dir: str, goal: str, hitl: bool = False, budgets: dict | None = None):
    """Runs one goal to completion (or escalation) under the given run_id,
    yielding the same per-step `{node_name: node_update}` dicts
    `graph.stream(..., stream_mode="updates")` yields.

    This is the shared core between the CLI driver (`run_cli`) and any UI
    that wants live per-node progress -- see `ui/coding_engineer_panel.py`,
    which streams these updates into a `st.status` box. Pulled out during
    the app.py integration once it became clear the CLI's inline loop
    would otherwise have to be duplicated for the UI.
    """
    graph = CodingEngineer().create_graph()
    initial_state: CodingLoopState = {
        "run_id": run_id,
        "target_dir": str(Path(target_dir).resolve()),
        "goal": goal,
        "hitl_bdd_approval": hitl,
        "budgets": budgets or {},
    }
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 150}
    yield from graph.stream(initial_state, config=config, stream_mode="updates")


def run_cli(target_dir: str, goal: str, hitl: bool = False, budgets: dict | None = None) -> str:
    """Runs one goal to completion (or escalation) and returns the run_id."""
    run_id = new_run_id()
    print(f"run_id={run_id}")
    final_status = None
    for update in stream_run(run_id, target_dir, goal, hitl=hitl, budgets=budgets):
        for node_name, node_update in update.items():
            if node_name == "__interrupt__":
                print(f"[INTERRUPTED] {node_update}")
                continue
            status = node_update.get("status") if isinstance(node_update, dict) else None
            print(f"[{node_name}] status={status}")
            final_status = status or final_status

    report_path = _loop_state_dir() / "state" / "coding-engineer" / run_id / "run-report.md"
    print(f"final status: {final_status}")
    print(f"report: {report_path}")
    return run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Coding Engineer agent from the CLI.")
    parser.add_argument("--target", default=str(Path(__file__).parent / "sample_target"))
    parser.add_argument(
        "--goal",
        default=(
            "In the target directory, implement the string-calculator kata so all scenarios "
            "in features/calculator.feature pass."
        ),
    )
    parser.add_argument("--hitl", action="store_true", help="Enable the optional author_bdd HITL pause.")
    args = parser.parse_args()

    run_cli(args.target, args.goal, hitl=args.hitl)
