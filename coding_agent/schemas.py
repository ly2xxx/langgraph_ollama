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


class BddRelevanceVerdict(BaseModel):
    """author_bdd's adoption gate: do the `.feature` files already present in
    the target actually describe THIS run's goal?

    Exists because of run 20260808T231438: a feature file committed by an
    unrelated run a week earlier was adopted wholesale as the frozen definition
    of done. Its scenarios passed on arrival, so no failing test ever drove a
    code change, and the run escalated with an empty diff after burning two
    sound plans."""

    covers_goal: bool = Field(
        description="True only if these scenarios actually test the stated goal and acceptance criteria. "
        "False if they describe different behaviour, a different module, or an unrelated earlier task -- "
        "even if they are well written and currently passing."
    )
    reason: str = Field(
        description="One sentence: what these scenarios test, and why that does or does not match the goal."
    )
    uncovered_criteria: list[str] = Field(
        default_factory=list,
        description="Acceptance criteria that no adopted scenario checks. A non-empty list is strong "
        "evidence for covers_goal=False.",
    )


class PlanIdea(BaseModel):
    """One candidate strategy from plan_tot's ToT propose step."""

    steps: list[str] = Field(description="Ordered, concrete steps to satisfy the goal.")
    rationale: str = Field(description="One or two sentences: why this approach, and its main risk.")


class PlanProposal(BaseModel):
    """plan_tot's propose step: k distinct candidate plans (primary role,
    higher temperature). CODING_ENGINEER.md §3.6 ToT."""

    plans: list[PlanIdea] = Field(description="Distinct candidate plans -- genuinely different approaches, not rewordings.")


class PlanScore(BaseModel):
    plan_index: int = Field(description="0-based index into the proposed plans list.")
    score: float = Field(description="Composite 0-10: goal-fit, simplicity, risk, testability. Higher is better.")
    reasoning: str = Field(description="One sentence justifying the score.")


class PlanJudgement(BaseModel):
    """plan_tot's evaluate step: the secondary-role judge scoring each proposed
    plan (maker/checker split applied to planning). CODING_ENGINEER.md §3.6."""

    scores: list[PlanScore] = Field(description="One score per proposed plan, by index.")


class ReviewFinding(BaseModel):
    location: str = Field(description="Where the problem is, as file:symbol or file:line.")
    severity: str = Field(description="One of: blocker | major | minor. Only blocker/major can force a reject.")
    rationale: str = Field(description="Why this is a problem -- especially a test that passes the letter but not the spirit.")
    suggested_fix: str = Field(description="Concrete direction for the next attempt.")


class ReviewVerdict(BaseModel):
    """review (checker) output. CODING_ENGINEER.md §3.3: adversarial audit of
    the diff vs the spec and step defs -- structured, never prose."""

    verdict: str = Field(
        description="One of: approve | approve_with_notes | reject. "
        "reject ONLY if there is at least one blocker/major finding; minor-only findings -> approve_with_notes."
    )
    findings: list[ReviewFinding] = Field(
        default_factory=list, description="Problems found. Empty for a clean approve."
    )


class DiagnosisResult(BaseModel):
    """diagnose's structured read of a failed attempt (CODING_ENGINEER.md §3.3).
    The failure_signature (§3.4) is computed in code from the traceback, NOT
    here -- this call only classifies the failure and distils a one-line lesson
    the next attempt can learn from. Routing is pure code; category only
    affects whether a `flake` gets its one free retry."""

    category: str = Field(
        description="One of: syntax | test-logic | env | flake | design. "
        "'syntax' = the code doesn't parse/import; 'test-logic' = the implementation is wrong; "
        "'env' = missing dependency/config/network, not the code's fault; "
        "'flake' = non-deterministic (timing/order/random) and would plausibly pass on a re-run; "
        "'design' = the approach itself can't satisfy the criteria without rethinking the plan."
    )
    insight: str = Field(
        description="One sentence the next attempt can act on -- what went wrong and the direction of the fix. "
        "Concrete, not a restatement of the error."
    )
