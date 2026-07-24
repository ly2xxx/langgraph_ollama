"""Structured-output schemas for the Coding Engineer agent's LLM calls.

Kept in one place so intake, author_bdd, and (from Phase 2/3 onward)
plan_tot/diagnose/review all draw from a single, consistent set of
contracts instead of ad hoc dicts. See CODING_ENGINEER.md §3.2-3.3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TargetSpec(BaseModel):
    """intake's structured read of the goal — the suitability gate at
    runtime (CODING_ENGINEER.md §1: "the intake node rejects goals it
    cannot turn into checkable scenarios")."""

    is_suitable: bool = Field(
        description="False if the goal cannot be turned into checkable acceptance criteria "
        "(too vague, an architecture decision, auth/payment code, a deploy, etc.)."
    )
    rejection_reason: str | None = Field(
        default=None, description="Why the goal was rejected, if is_suitable is False. Omit otherwise."
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Checkable statements the finished code must satisfy. Empty if is_suitable is False.",
    )
    in_scope_files: list[str] = Field(
        default_factory=list,
        description="Glob patterns (relative to the target directory) for files the maker is expected to touch.",
    )
    test_command: str = Field(
        default="pytest -q",
        description="The command that should be treated as the fast self-check for this goal.",
    )
    constraints: list[str] = Field(
        default_factory=list, description="Explicit things the maker must not do."
    )


class BddAuthorResult(BaseModel):
    """author_bdd's structured output when it has to draft new scenarios —
    i.e. no existing `.feature` file was found already in the target."""

    feature_gherkin: str = Field(description="Full contents of a .feature file, valid Gherkin syntax.")
    feature_relative_path: str = Field(
        description="Where to write the feature file, relative to the worktree root, e.g. 'features/goal.feature'."
    )
    step_defs_python: str = Field(
        description="Full contents of a pytest-bdd step-definitions module implementing every step in "
        "feature_gherkin, importing the module(s) under test from the worktree."
    )
    step_defs_relative_path: str = Field(
        description="Where to write the step-definitions file, relative to the worktree root, "
        "e.g. 'features/steps/test_goal_steps.py'."
    )
    ambiguity: bool = Field(
        description="True only if a reasonable second reading of the goal would produce materially "
        "different scenarios — i.e. genuinely worth a human's five seconds before freezing. "
        "False for anything you can reasonably infer; do not set this just to be safe."
    )
    ambiguity_reason: str | None = Field(
        default=None, description="One sentence: what's ambiguous and what the two readings would be."
    )
