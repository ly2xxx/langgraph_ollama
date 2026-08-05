"""State schema, budgets, and small shared helpers for the Coding Engineer loop.

Extracted from ``coding_agent/engine.py`` during the single-responsibility
refactor (CODING_ENGINEER.md §3.2).  These are the leaf definitions every
other submodule builds on -- no LLM calls, no graph nodes, no subprocesses.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages

from coding_agent.tools.worktree import WorktreeHandle

# Display/telemetry label for this agent. Defined here (not in app.py) so the
# panel can import it without a circular dependency on app.py.
CODING_ENGINEER_LABEL = "Coding Engineer"

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
    category: str | None  # added Phase 2 -- diagnose's LLM classification
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
    model_info: dict  # added in Phase 1 follow-up -- models.describe_all(), for the report/UI
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
    tokens_used: int  # Phase 4 -- best-effort running tally for the token budget (§3.4)
    run_started_at: float  # added in Phase 1 -- see module docstring
    last_diff: str
    test_report: dict
    bdd_report: dict
    review_result: dict | None  # renamed from `review` -- can't share a name with the review node
    escalation_reason: str | None  # added in Phase 1 -- see module docstring
    # no-progress detection (Phase 2 -- CODING_ENGINEER.md §3.4)
    failure_signature: str | None  # this attempt's signature
    prev_failure_signature: str | None  # last attempt's, for the "same twice" check
    exhausted_plan_ids: list[str]  # plans killed by no-progress
    flake_free_retries: int  # free retries already spent on `flake` classifications
    diagnosis: dict | None  # diagnose's per-attempt verdict incl. the routing action
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