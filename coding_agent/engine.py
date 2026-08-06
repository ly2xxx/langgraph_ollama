"""Coding Engineer — the non-stop coding agent's LangGraph graph.

This module is the main entrypoint and backward-compatibility layer after
the single-responsibility refactor.  The implementation now lives in focused
submodules under ``coding_agent/``:

- ``coding_agent/state.py``        — state schema, budgets, small helpers.
- ``coding_agent/llm_boundaries.py``— isolated LLM invocation wrappers.
- ``coding_agent/gates.py``        — quality-gate logic and differential linting.
- ``coding_agent/maker_tools.py``  — maker tool construction and task text.
- ``coding_agent/nodes.py``        — StateGraph node implementations + routing.

Everything that used to be importable from ``coding_agent.engine`` is still
importable from here (re-exported below), so existing imports across
``app.py``, ``ui/``, and ``tests/test_engine.py`` keep working unchanged --
including the monkeypatch surfaces tests rely on (``_llm_parse_target_spec``,
``_llm_author_bdd``, ``_run_maker``, ``_llm_propose_plans``, ``_llm_judge_plans``,
``_llm_review``, ``_llm_diagnose``, ``get_llm``, etc.).

Phase 1 scope (CODING_ENGINEER.md §6): the linear loop —
intake -> author_bdd -> plan_tot (single fixed plan) -> code -> self_check
-> bdd_gate -> finalize, with a diagnose stub that retries on failure up to
a budget, then escalates. No plan-switching (ToT/GoT, Phase 3), no
signature-based no-progress detection (Phase 2), no adversarial reviewer
(Phase 3) yet — see PHASED_PLAN.md for exactly what each phase added.

Every LLM call goes through a small boundary function (`_llm_parse_target_spec`,
`_llm_author_bdd`, `_run_maker`) so tests can monkeypatch just the model call
and exercise the real graph, worktree, gates, and report writer around it.
"""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

import telemetry
from coding_agent.models import describe_all, get_llm
from coding_agent.report import stop_flag_set, write_run_report
from coding_agent.schemas import (
    BddAuthorResult,
    DiagnosisResult,
    PlanJudgement,
    PlanProposal,
    ReviewVerdict,
    TargetSpec,
)
from coding_agent.signatures import (
    compute_signature,
    extract_failures,
    review_signature,
    signature_for_failure,
    template_message,
)
from coding_agent.structured import StructuredOutputError, invoke_structured
from coding_agent.tools.code_exec import Jail, JailViolation, run_command
from coding_agent.tools.worktree import WorktreeHandle, create_worktree
from coding_agent.tools.worktree import changed_files as worktree_changed_files
from coding_agent.tools.worktree import commit as worktree_commit
from coding_agent.tools.worktree import diff as worktree_diff
from coding_agent.tools.worktree import file_at_baseline as worktree_file_at_baseline
from coding_agent.tools.worktree import renamed_paths as worktree_renamed_paths

# -- state.py re-exports ---------------------------------------------------
from coding_agent.state import (  # noqa: F401
    CODING_ENGINEER_LABEL,
    DEFAULT_BUDGETS,
    Budgets,
    CodingLoopState,
    Lesson,
    Plan,
    _handle_from_state,
    _loop_state_dir,
    _status_message,
)

# -- gates.py re-exports ---------------------------------------------------
from coding_agent.gates import (  # noqa: F401
    _harness_exclude_dirs,
    _is_under_any,
    _read_failures,
    _read_json_report,
    _read_step_defs,
    _render_ruff_findings,
    _ruff_new_findings,
    _run_ruff_json,
)

# -- maker_tools.py re-exports ---------------------------------------------
from coding_agent.maker_tools import _build_maker_tools, _maker_task_text  # noqa: F401

# -- llm_boundaries.py re-exports ------------------------------------------
from coding_agent.llm_boundaries import (  # noqa: F401
    _criteria_text,
    _lessons_block,
    _llm_author_bdd,
    _llm_diagnose,
    _llm_judge_plans,
    _llm_parse_target_spec,
    _llm_propose_plans,
    _llm_review,
    _run_maker,
)

# -- nodes.py re-exports ---------------------------------------------------
from coding_agent.nodes import (  # noqa: F401
    _append_lesson,
    _diagnose_llm,
    _failed_phase,
    _fallback_plan,
    _MAX_FLAKE_FREE_RETRIES,
    _route_after_author_bdd,
    _route_after_bdd_gate,
    _route_after_diagnose,
    _route_after_intake,
    _route_after_review,
    _route_after_self_check,
    _score_plans,
    _signature_and_detail,
    _summarize_failure,
    author_bdd_node,
    bdd_gate_node,
    code_node,
    diagnose_node,
    escalate_node,
    finalize_node,
    intake_node,
    plan_tot_node,
    review_node,
    self_check_node,
)


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
    graph.add_node("review", review_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", _route_after_intake, {"author_bdd": "author_bdd", "escalate": "escalate"})
    graph.add_conditional_edges(
        "author_bdd", _route_after_author_bdd, {"plan_tot": "plan_tot", "escalate": "escalate"}
    )
    graph.add_edge("plan_tot", "code")
    graph.add_edge("code", "self_check")
    graph.add_conditional_edges("self_check", _route_after_self_check, {"bdd_gate": "bdd_gate", "diagnose": "diagnose"})
    graph.add_conditional_edges("bdd_gate", _route_after_bdd_gate, {"review": "review", "diagnose": "diagnose"})
    graph.add_conditional_edges("review", _route_after_review, {"finalize": "finalize", "diagnose": "diagnose"})
    graph.add_conditional_edges(
        "diagnose", _route_after_diagnose, {"code": "code", "plan_tot": "plan_tot", "escalate": "escalate"}
    )
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
        # Resolved once up front (not re-derived per node) so the report and
        # any UI show exactly what this run actually used, even if env vars
        # change between this run and the next one.
        "model_info": describe_all(),
    }
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 150}
    yield from graph.stream(initial_state, config=config, stream_mode="updates")


def run_cli(target_dir: str, goal: str, hitl: bool = False, budgets: dict | None = None, run_id: str | None = None) -> str:
    """Runs one goal to completion (or escalation) and returns the run_id."""
    telemetry.init_telemetry()
    run_id = run_id or new_run_id()
    print(f"run_id={run_id}")
    models = describe_all()
    print(f"primary model: {models['primary']}")
    print(f"secondary model: {models['secondary']}")
    primary_model = (models.get("primary") or {}).get("model") or "unknown"
    final_status = None
    with telemetry.track_request("Coding Engineer CLI", primary_model, run_id=run_id):
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
    parser.add_argument("--run-id", help="Resume an existing run by providing its run_id.")
    args = parser.parse_args()

    run_cli(args.target, args.goal, hitl=args.hitl, run_id=args.run_id)