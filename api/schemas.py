"""Request/response models. Field descriptions surface as Swagger help text."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Budgets(BaseModel):
    """The agent's stop rails. Omit to use the engine's defaults."""
    max_attempts_per_plan: int = Field(3, ge=1, le=20, description="Coding attempts before the active plan is abandoned.")
    max_plans: int = Field(3, ge=1, le=6, description="Tree-of-thought candidate plans proposed per planning round.")
    max_total_attempts: int = Field(9, ge=1, le=50)
    cmd_timeout_s: int = Field(120, ge=10, le=600, description="Per-command timeout for the agent's own test/lint runs.")
    wall_clock_s: int = Field(1800, ge=60, le=7200, description="Hard wall-clock budget for the whole run.")
    token_budget: int = Field(0, ge=0, description="0 = unlimited.")


class StartRunRequest(BaseModel):
    target_dir: str = Field(
        ...,
        description="Local folder to work on. Must be inside a git repo: the agent "
                    "branches a worktree off HEAD, so uncommitted changes are NOT visible to it. "
                    "Browse with GET /folders.",
        examples=["H:/code/yl/langgraph_ollama"],
    )
    goal: str = Field(
        ...,
        min_length=10,
        description="What to change, in plain English. Concrete and checkable beats vague.",
        examples=["Extract the duplicate model-construction logic in app.py into a helper and update call sites."],
    )
    test_style: Literal["bdd", "pytest"] = Field(
        "bdd",
        description=(
            "How the definition of done is expressed.\n\n"
            "**bdd** (default): a Gherkin feature file plus pytest-bdd step definitions are "
            "authored up front and frozen, then run by the bdd_gate.\n\n"
            "**pytest**: skips authoring entirely. Intake's acceptance criteria are the "
            "definition of done and the agent writes plain pytest tests alongside the code, "
            "checked by self_check. Use this when a model cannot reliably produce the BDD "
            "artefact — authoring a whole feature file plus a step-definitions module in one "
            "structured call is the largest and most brittle request in the loop."
        ),
    )
    budgets: Budgets | None = Field(None, description="Omit for engine defaults.")
    primary_model: str | None = Field(None, description="Override CODING_AGENT_PRIMARY_MODEL for this run.")
    secondary_model: str | None = Field(None, description="Override the judge/reviewer model for this run.")


class StartRunResponse(BaseModel):
    run_id: str
    status: str
    target_dir: str
    goal: str
    poll: str = Field(description="GET this for progress.")
    note: str = Field(
        description="Where the output goes. Your target folder is NOT modified.")


class NodeEvent(BaseModel):
    seq: int
    node: str
    status: str | None = None
    note: str | None = None
    at: float = Field(description="Unix timestamp.")


class RunSummary(BaseModel):
    run_id: str
    status: Literal["running", "done", "escalated", "failed", "stopping"]
    goal: str
    test_style: str = "bdd"
    target_dir: str
    started_at: float
    finished_at: float | None = None
    duration_s: float | None = None
    event_count: int
    error: str | None = Field(None, description="Set when the run raised rather than finishing.")


class RunDetail(RunSummary):
    outcome: str | None = None
    escalation_reason: str | None = None
    attempts: int | None = None
    worktree_dir: str | None = None
    branch: str | None = None
    changed_files: list[str] = []
    report_path: str | None = None
    events: list[NodeEvent] = []


class FolderEntry(BaseModel):
    name: str
    path: str
    is_git_repo: bool


class FolderListing(BaseModel):
    path: str
    parent: str | None
    is_git_repo: bool
    git_root: str | None = Field(None, description="Repo root, or null if not inside a git repo.")
    uncommitted: list[str] = Field(default_factory=list,
                                   description="Uncommitted paths — NOT visible to the agent, which branches from HEAD.")
    entries: list[FolderEntry]


class ModelInfo(BaseModel):
    primary: dict[str, Any]
    secondary: dict[str, Any]
