"""StateGraph node implementations and conditional routing for the Coding Engineer loop.

Extracted from ``coding_agent/engine.py`` during the single-responsibility
refactor.  Each node is a thin orchestrator: it calls a boundary function
(``coding_agent.llm_boundaries``), runs a gate (``coding_agent.gates``), or
does pure-code state bookkeeping, then returns a state update dict.

Monkeypatch compatibility: tests patch boundary functions and ``get_llm`` on
the ``coding_agent.engine`` module (e.g. ``coding_agent.engine._run_maker``).
So that those patches take effect, nodes look up those callables through the
engine module at *call time* via the lazy ``_eng()`` accessor below, rather
than holding local references that would bypass the patch.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from langgraph.types import interrupt

from coding_agent.gates import (
    _harness_exclude_dirs,
    _is_under_any,
    _read_failures,
    _read_json_report,
    _render_ruff_findings,
    _ruff_new_findings,
)
from coding_agent.report import stop_flag_set, write_run_report
from coding_agent.schemas import ReviewVerdict
from coding_agent.signatures import (
    compute_signature,
    review_signature,
    signature_for_failure,
    template_message,
)
from coding_agent.state import (
    DEFAULT_BUDGETS,
    CodingLoopState,
    Plan,
    _handle_from_state,
    _loop_state_dir,
    _status_message,
)
from coding_agent.structured import StructuredOutputError
from coding_agent.tools.code_exec import Jail, run_command
from coding_agent.tools.worktree import (
    create_worktree,
    changed_files as worktree_changed_files,
    commit as worktree_commit,
    diff as worktree_diff,
)

try:
    # telemetry lives at the repo root; it's optional and degrades to no-ops.
    # Used here only for its pure token-usage extractor (no OTel import), so a
    # token tally can ride in graph state and feed the §3.4 token budget.
    from telemetry import extract_token_usage as _extract_token_usage
except Exception:  # noqa: BLE001 -- telemetry is optional; never let its absence break the engine
    def _extract_token_usage(_graph_output) -> tuple[int, int]:
        return 0, 0


# ---------------------------------------------------------------------------
# lazy engine accessor -- see module docstring for why this exists
# ---------------------------------------------------------------------------

_engine = None


def _eng():
    """Return the ``coding_agent.engine`` module, importing it lazily.

    ``engine`` imports ``nodes`` at module load time, so ``nodes`` cannot
    import ``engine`` at its own module level (circular).  By the time any
    node *runs*, ``engine`` is fully loaded, so this lazy lookup is safe and
    lets tests monkeypatch attributes on ``coding_agent.engine`` (e.g.
    ``_run_maker``, ``get_llm``) and have the patches take effect here.
    """
    global _engine
    if _engine is None:
        import coding_agent.engine as e
        _engine = e
    return _engine


# ---------------------------------------------------------------------------
# small node-local helpers
# ---------------------------------------------------------------------------


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


def _fallback_plan() -> Plan:
    return {
        "id": "plan-1",
        "steps": ["Implement the goal against the acceptance criteria; iterate using self_check/bdd_gate feedback."],
        "rationale": "fallback single plan (propose/judge unavailable)",
        "score": 1.0,
        "status": "untried",
    }


##### 6b. ToT Judge Scoring: Secondary model (temp 0.0) cold evaluation against accumulated lessons
def _score_plans(state: CodingLoopState, plans: list[Plan], exclude: set[str]) -> list[Plan]:
    """Judge (secondary role, temperature 0) scores the not-yet-exhausted plans.
    On re-entry the aggregated lessons ride along in the prompt -- the GoT step,
    so a plan that would repeat a known dead end scores low. Degrades gracefully:
    if the judge call fails, keep any existing scores and otherwise fall back to
    proposal order (first proposed = best)."""
    to_score = [p for p in plans if p["id"] not in exclude]
    if not to_score:
        return plans
    secondary = _eng().get_llm("secondary", temperature=0.0)
    try:
        judgement = _eng()._llm_judge_plans(secondary, state, to_score)
        by_index = {s.plan_index: s.score for s in judgement.scores}
        for i, p in enumerate(to_score):
            if i in by_index:
                p["score"] = float(by_index[i])
    except StructuredOutputError:
        for i, p in enumerate(to_score):
            if not p.get("score"):
                p["score"] = float(len(to_score) - i)
    return plans


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


##### 4. State Machine Node 1/10: Intake (Goal evaluation & worktree initialization)
def intake_node(state: CodingLoopState) -> dict:
    budgets = {**DEFAULT_BUDGETS, **(state.get("budgets") or {})}
    llm = _eng().get_llm("primary")
    try:
        spec = _eng()._llm_parse_target_spec(llm, state["goal"], state["target_dir"])
    except StructuredOutputError as exc:
        # Escalate gracefully (with a report) instead of letting the raw
        # exception blow up the graph -- the first live run surfaced exactly
        # this as an unhandled stack trace in the UI. See structured.py.
        return {
            "budgets": budgets,
            "run_started_at": time.time(),
            "status": "escalated",
            "escalation_reason": f"intake structured-output failure: {exc}",
            "messages": [_status_message("intake", False, note=str(exc)[:200])],
        }

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


def _route_after_author_bdd(state: CodingLoopState) -> str:
    return "escalate" if state.get("status") == "escalated" else "plan_tot"


##### 5. State Machine Node 2/10: BDD Authoring (Definition of done frozen before code exists)

# Cap the per-file text sent to the adoption gate: enough to judge relevance
# from the Feature/Scenario lines, small enough that a directory full of
# leftovers can't blow the context window.
_MAX_ADOPT_FEATURE_CHARS = 4000


def _adoptable_feature_paths(worktree_dir: Path) -> list[str]:
    """`.feature` files already in the target, as adoption candidates.

    Bug found on the first real self-hosted run: an unscoped rglob picked up
    coding_agent/sample_target/features/calculator.feature -- the agent's own
    demo fixture -- and froze it as the "definition of done" for an unrelated
    goal (moving rag_research_chatbot.py). Same harness-exclusion rule as
    self_check/bdd_gate (_harness_exclude_dirs), applied here too now.

    `.loop` is excluded on top of that: it holds this agent's own run state,
    including a full worktree checkout per previous run. Left in, a target that
    had been worked on before offered up every feature file every earlier run
    had ever frozen -- on the sample_target fixture alone that is five
    candidates rather than one, most of them copies of contracts for goals long
    since finished. Adoption must never see run artefacts; that is the whole
    lesson of run 20260808T231438 (see _adopt_existing_features)."""
    harness_excludes = set(_harness_exclude_dirs(worktree_dir)) | {".git", ".loop"}
    return sorted(
        str(p.relative_to(worktree_dir)).replace(os.sep, "/")
        for p in worktree_dir.rglob("*.feature")
        if not harness_excludes & set(p.relative_to(worktree_dir).parts)
    )


def _read_capped(path: Path, limit: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= limit else f"{text[:limit]}\n... (truncated)"


def _adopt_existing_features(state: CodingLoopState, worktree_dir: Path, existing: list[str]) -> dict | None:
    """Decide whether pre-existing feature files become this run's frozen contract.

    Returns a node state-update (adopt, or escalate), or None meaning "these
    describe some other goal -- draft fresh scenarios instead".

    The harness exclusion in `_adoptable_feature_paths` stopped the agent
    adopting its own *fixtures*, but not the artefacts of its own earlier
    *runs*: run 20260808T231438 adopted features/rag_agent_move.feature --
    committed to the repo by a run a week before -- as the definition of done
    for an unrelated AgentExecutor migration. Those scenarios passed on arrival,
    so self_check and bdd_gate were green before the maker touched anything, no
    failing test ever drove a code change, and the run escalated with an empty
    diff having retired two sound plans for a fault neither one caused.
    Provenance can't be read off the filesystem, so the *content* is checked
    against the goal instead."""
    features = [(p, _read_capped(worktree_dir / p, _MAX_ADOPT_FEATURE_CHARS)) for p in existing]
    llm = _eng().get_llm("secondary", temperature=0.0)  # checker role: a judgement, not authoring
    try:
        verdict = _eng()._llm_check_bdd_relevance(llm, state, features)
    except StructuredOutputError as exc:
        # Fail closed. Adopting unchecked is the bug this gate exists to stop,
        # and silently drafting over a repo's real feature suite is its own kind
        # of surprise -- so stop and let a human look.
        return {
            "status": "escalated",
            "escalation_reason": f"author_bdd adoption check structured-output failure: {exc}",
            "messages": [_status_message("author_bdd", False, note=str(exc)[:200])],
        }

    if not verdict.covers_goal:
        return None

    adopted = existing
    if state.get("hitl_bdd_approval"):
        # Adoption is the one path that freezes a contract from files this run
        # did not write and cannot vet for provenance, so it gets the human
        # checkpoint whenever HITL is on -- not only when the model is unsure.
        # (The authoring path pauses on `ambiguity` instead.)
        payload = interrupt(
            {
                "node": "author_bdd",
                "decision": "adopt_existing_features",
                "reason": verdict.reason,
                "uncovered_criteria": verdict.uncovered_criteria,
                "feature_paths": adopted,
            }
        )
        if isinstance(payload, dict):
            if payload.get("approved") is False:
                return {
                    "status": "escalated",
                    "escalation_reason": "human rejected the pre-existing BDD scenarios at author_bdd",
                    "messages": [_status_message("author_bdd", False, note="adoption rejected by human")],
                }
            adopted = payload.get("feature_paths", adopted)

    return {
        "feature_paths": adopted,
        "status": "planning",
        "messages": [_status_message("author_bdd", True, note=f"adopted existing: {', '.join(adopted)}")],
    }


def author_bdd_node(state: CodingLoopState) -> dict:
    worktree_dir = Path(state["worktree_dir"])
    existing = _adoptable_feature_paths(worktree_dir)

    if existing:
        adopted = _adopt_existing_features(state, worktree_dir, existing)
        if adopted is not None:
            return adopted
        # Fall through and draft fresh scenarios. The rejected files stay on
        # disk and bdd_gate will still collect them (it scopes by directory),
        # but they are no longer the contract -- and since the drafted scenarios
        # fail until the goal is actually implemented, the gate can no longer go
        # vacuously green on someone else's passing tests.

    llm = _eng().get_llm("primary", temperature=0.3)
    try:
        result = _eng()._llm_author_bdd(llm, state)
    except StructuredOutputError as exc:
        return {
            "status": "escalated",
            "escalation_reason": f"author_bdd structured-output failure: {exc}",
            "messages": [_status_message("author_bdd", False, note=str(exc)[:200])],
        }

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


##### 6. State Machine Node 3/10: Plan ToT (Tree-of-Thought planning & Graph-of-Thought recovery)
def plan_tot_node(state: CodingLoopState) -> dict:
    """Tree-of-Thought planning (CODING_ENGINEER.md §3.6). First entry: the
    primary model proposes k distinct plans (hot), the secondary-role judge
    scores them (cold), and the best untried plan becomes active. Re-entry
    (after diagnose retires a stalled plan): the surviving candidates are
    RE-SCORED with the aggregated lessons in the prompt -- not regenerated --
    and the next best untried plan is selected."""
    budgets = state["budgets"]
    k = budgets.get("max_plans", 3)
    exhausted = set(state.get("exhausted_plan_ids") or [])
    existing = list(state.get("candidate_plans") or [])

    if not existing:
        primary = _eng().get_llm("primary", temperature=0.8)
        try:
            proposal = _eng()._llm_propose_plans(primary, state, k)
            existing = [
                {"id": f"plan-{i + 1}", "steps": list(p.steps), "rationale": p.rationale, "score": 0.0,
                 "status": "untried"}
                for i, p in enumerate(proposal.plans)
            ] or [_fallback_plan()]
        except StructuredOutputError:
            existing = [_fallback_plan()]

    existing = _score_plans(state, existing, exclude=exhausted)

    candidates = [p for p in existing if p["id"] not in exhausted]
    if not candidates:  # defensive -- diagnose escalates before this can happen
        return {
            "candidate_plans": existing,
            "status": "escalated",
            "escalation_reason": "no_plans_left",
            "diagnosis": {"action": "escalate"},
        }

    best = max(candidates, key=lambda p: p.get("score", 0.0))
    for p in existing:
        p["status"] = "active" if p["id"] == best["id"] else ("exhausted" if p["id"] in exhausted else "untried")

    return {
        "candidate_plans": existing,
        "active_plan_id": best["id"],
        "status": "coding",
        "attempt": 0,  # each plan gets its own per-plan attempt budget
        "messages": [
            _status_message("plan_tot", True, note=f"selected {best['id']} (score {best.get('score', 0):.1f}) of {len(existing)}")
        ],
    }


##### 8. State Machine Node 4/10: Code Execution (Maker model executes code with frozen acceptance tests in Jail)
def code_node(state: CodingLoopState) -> dict:
    jail = Jail(root=Path(state["worktree_dir"]), frozen=frozenset(Path(p) for p in state.get("feature_paths", [])))
    llm = _eng().get_llm("primary", temperature=0.2)
    maker_result = _eng()._run_maker(llm, jail, state)

    handle = _handle_from_state(state)
    diff_text = worktree_diff(handle)

    summary = maker_result.get("output", "") if isinstance(maker_result, dict) else str(maker_result)
    # Best-effort token tally: the maker (AgentExecutor) is where the bulk of
    # tokens go, and its result may carry usage on the final AIMessage. Ollama
    # often omits usage on tool-calling turns, so this under-counts rather than
    # over-counts -- the token budget stays a safety valve, not a precise meter.
    p_tok, c_tok = _extract_token_usage(maker_result if isinstance(maker_result, dict) else {})
    return {
        "last_diff": diff_text,
        "tokens_used": state.get("tokens_used", 0) + p_tok + c_tok,
        "status": "coding",
        # A new attempt invalidates any prior review verdict -- clear it so
        # diagnose (Phase 3) doesn't mistake a stale reject for this attempt's
        # outcome when a later gate fails first.
        "review_result": None,
        "messages": [_status_message("code", True, note=str(summary)[:200])],
    }


##### 10. State Machine Node 5/10: Self Check (Differential ruff linting & pytest unit tests)
def self_check_node(state: CodingLoopState) -> dict:
    worktree_dir = Path(state["worktree_dir"])
    timeout = state["budgets"]["cmd_timeout_s"]
    harness_excludes = _harness_exclude_dirs(worktree_dir)

    # Scope ruff to files changed this run AND only fail on findings this run
    # introduced (see _ruff_new_findings for the full why). Two live-run bugs
    # drove this: (1) an unscoped `ruff check .` failed on pre-existing debt in
    # files the maker never touched; (2) scoping to changed files still failed
    # on pre-existing debt in a file the maker legitimately *had* to touch
    # (app.py's import line). Differential-vs-baseline forgives both.
    #
    # Also exclude the frozen BDD harness (the feature dir + its step defs) and
    # the agent's own package: those aren't the maker's implementation change.
    # author_bdd *generates* the step-defs file, and it routinely leaves an
    # unused `import pytest` in it (F401) -- that's bdd_gate's code to run, not
    # self_check's to lint. The live RAG POC's move actually completed, and the
    # ONLY thing blocking finalization was self_check flagging F401 in that
    # generated step-defs file.
    excluded_dirs = set(harness_excludes) | {
        str(Path(fp).parent).replace(os.sep, "/") for fp in state.get("feature_paths", [])
    }
    handle = _handle_from_state(state)
    changed = [
        p
        for p in worktree_changed_files(handle)
        if (worktree_dir / p).exists() and p.endswith(".py") and not _is_under_any(p, excluded_dirs)
    ]

    new_findings, ruff_result = _ruff_new_findings(worktree_dir, changed, handle, harness_excludes, timeout)
    if new_findings is None:
        # Couldn't parse ruff's json (or it timed out) -> fall back to an opaque
        # rc check on the changed files, so a broken ruff invocation fails safe
        # rather than silently passing.
        fallback = run_command(
            "ruff",
            ["check", *(changed or ["."]), "--select", "E9,F", "--per-file-ignores", "__init__.py:F401",
             *[f"--extend-exclude={d}" for d in harness_excludes]],
            cwd=worktree_dir,
            timeout_s=timeout,
        )
        ruff_returncode = fallback.returncode
        ruff_stdout = fallback.stdout
        ruff_stderr = fallback.stderr
        ruff_timed_out = fallback.timed_out
        ruff_passed = fallback.returncode == 0 and not fallback.timed_out
    else:
        ruff_returncode = 1 if new_findings else 0
        ruff_stdout = _render_ruff_findings(new_findings)
        ruff_stderr = ruff_result.stderr if ruff_result else ""
        ruff_timed_out = ruff_result.timed_out if ruff_result else False
        ruff_passed = not new_findings

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
    failures = _read_failures(report_file)
    report_file.unlink(missing_ok=True)

    # pytest exits 5 when it collects zero tests -- expected when the only
    # tests in scope ARE the frozen BDD scenarios (self_check ignores them;
    # bdd_gate is the node responsible for actually finding and running them).
    pytest_ok = pytest_result.returncode in (0, 5) and not pytest_result.timed_out
    passed = ruff_passed and pytest_ok

    test_report = {
        "ruff": {
            "returncode": ruff_returncode,
            "stdout": ruff_stdout,
            "stderr": ruff_stderr,
            "timed_out": ruff_timed_out,
        },
        "pytest": {
            "returncode": pytest_result.returncode,
            "stdout": pytest_result.stdout,
            "stderr": pytest_result.stderr,
            "timed_out": pytest_result.timed_out,
            "summary": summary,
            "failures": failures,  # normalised for signing -- see signatures.py / diagnose
        },
        # ruff findings are signable too (a ruff-only self_check failure has no
        # pytest failure): the sorted rule codes are a stable descriptor.
        "ruff_codes": sorted({f.get("code") for f in (new_findings or []) if f.get("code")}),
        "passed": passed,
    }
    return {"test_report": test_report, "status": "testing", "messages": [_status_message("self_check", passed)]}


def _route_after_self_check(state: CodingLoopState) -> str:
    return "bdd_gate" if state["test_report"]["passed"] else "diagnose"


##### 11. State Machine Node 6/10: BDD Gate (Frozen BDD acceptance test verification)
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
    failures = _read_failures(report_file)
    report_file.unlink(missing_ok=True)

    passed = result.returncode == 0 and not result.timed_out
    bdd_report = {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "summary": summary,
        "failures": failures,  # normalised for signing -- see signatures.py / diagnose
        "passed": passed,
    }
    return {"bdd_report": bdd_report, "status": "testing", "messages": [_status_message("bdd_gate", passed)]}


def _route_after_bdd_gate(state: CodingLoopState) -> str:
    # Phase 3: a green bdd_gate no longer finalizes directly -- the adversarial
    # reviewer (checker) gets the last word (CODING_ENGINEER.md §3.1/§3.3).
    return "review" if state["bdd_report"]["passed"] else "diagnose"


##### 12. State Machine Node 7/10: Review (Adversarial reviewer on secondary model, temp 0.0, blinded to maker reasoning)
def review_node(state: CodingLoopState) -> dict:
    """Adversarial checker (CODING_ENGINEER.md §3.3), always the secondary role
    (§3.5) -- a different model catches more than a different prompt on the same
    one. Sees the spec, diff, step defs, and (green) test output, NOT the maker's
    reasoning, and specifically hunts trivial-pass hacks in the step defs.
    reject requires a blocker/major finding; minor-only downgrades to
    approve_with_notes (notes land in the report, run still finalizes)."""
    if stop_flag_set(state["run_id"], _loop_state_dir()):
        return {"status": "escalated", "escalation_reason": "stopped by user", "diagnosis": {"action": "escalate"}}

    secondary = _eng().get_llm("secondary", temperature=0.0)
    try:
        verdict = _eng()._llm_review(secondary, state)
    except StructuredOutputError:
        # A review hiccup must not block an already-green run -> approve with a note.
        verdict = ReviewVerdict(verdict="approve_with_notes", findings=[])

    blocking = [f for f in verdict.findings if f.severity in ("blocker", "major")]
    is_reject = verdict.verdict == "reject" and bool(blocking)
    review = {
        "verdict": "reject" if is_reject else ("approve_with_notes" if verdict.findings else "approve"),
        "findings": [f.model_dump() for f in verdict.findings],
        "blocking": [f.model_dump() for f in blocking],
    }
    note = f"{review['verdict']}" + (f" ({len(blocking)} blocking)" if blocking else "")
    return {"review_result": review, "status": "testing", "messages": [_status_message("review", not is_reject, note=note)]}


def _route_after_review(state: CodingLoopState) -> str:
    review = state.get("review_result") or {}
    return "diagnose" if review.get("verdict") == "reject" and review.get("blocking") else "finalize"


_MAX_FLAKE_FREE_RETRIES = 2  # a genuinely flaky gate shouldn't spin forever on "free" retries


def _failed_phase(state: CodingLoopState) -> str | None:
    """Which gate failed this attempt (closed set, matches §3.4's `phase`).
    A review reject is only 'this attempt's' failure because code_node clears
    the prior review at the start of every attempt, so a stale reject can't
    shadow a later self_check/bdd_gate failure."""
    review = state.get("review_result") or {}
    if review.get("verdict") == "reject" and review.get("blocking"):
        return "review"
    if not (state.get("test_report") or {}).get("passed", True):
        return "self_check"
    if not (state.get("bdd_report") or {}).get("passed", True):
        return "bdd_gate"
    return None


def _signature_and_detail(state: CodingLoopState, phase: str) -> tuple[str, str]:
    """(failure_signature, human detail) for the failed gate. Prefers the first
    failing pytest test (the §3.4 recipe); falls back to a stable descriptor for
    a ruff-only self_check failure (sorted rule codes) or an opaque gate error."""
    if phase == "self_check":
        report = state.get("test_report") or {}
        failures = (report.get("pytest") or {}).get("failures") or []
        if failures:
            f = failures[0]
            return signature_for_failure(phase, f), f"{f.get('nodeid')}: {f.get('message')}"
        codes = report.get("ruff_codes") or []
        detail = "ruff findings: " + (", ".join(codes) or ((report.get("ruff") or {}).get("stdout") or "")[:400])
        return compute_signature(phase, "ruff", "ruff", ",".join(sorted(codes)), ""), detail
    if phase == "review":
        review = state.get("review_result") or {}
        blocking = review.get("blocking") or []
        first = blocking[0] if blocking else {}
        # A maker/checker stalemate is no-progress by another name (§3.4): sign the
        # rejection by (location, severity) so a reviewer that keeps rejecting the
        # same spot is caught by the same "same signature twice" rule.
        sig = review_signature(first.get("location", ""), first.get("severity", ""))
        detail = "review reject: " + "; ".join(
            f"{f.get('severity')} {f.get('location')}: {f.get('rationale')}" for f in blocking[:3]
        )
        return sig, detail
    # bdd_gate
    report = state.get("bdd_report") or {}
    failures = report.get("failures") or []
    if failures:
        f = failures[0]
        return signature_for_failure(phase, f), f"{f.get('nodeid')}: {f.get('message')}"
    stdout = report.get("stdout") or ""
    return compute_signature(phase, "bdd", "bdd", template_message(stdout), ""), f"bdd_gate failed:\n{stdout[:400]}"


def _diagnose_llm(state: CodingLoopState, phase: str, detail: str) -> tuple[str, str]:
    """(category, insight) from the LLM, degrading gracefully: a structured-output
    hiccup in diagnose must never crash the loop, so on failure we fall back to
    an 'unknown' category (no free flake retry) and the code-only summary."""
    try:
        llm = _eng().get_llm("primary", temperature=0.0)
        result = _eng()._llm_diagnose(llm, state, phase, detail)
        return result.category, (result.insight or _summarize_failure(state))
    except Exception:  # noqa: BLE001 -- diagnose is best-effort; a model/network hiccup here must not crash the loop
        return "unknown", _summarize_failure(state)


def _append_lesson(state: CodingLoopState, attempt: int, plan_id: str, signature: str,
                   category: str, insight: str) -> list:
    lessons = list(state.get("lessons", []))
    lessons.append(
        {
            "attempt": attempt,
            "plan_id": plan_id,
            "failure_signature": signature,
            "category": category,
            "insight": insight,
        }
    )
    return lessons


##### 14. State Machine Node 8/10: Diagnose (Engineered stopping: failure signature, 2-plan exhaustion, budgets & flake retry)
def diagnose_node(state: CodingLoopState) -> dict:
    """Classify the failure, sign it (§3.4), and decide retry / escalate.

    Hard exits, in order (§3.4): stop flag; same signature twice in a row ->
    active plan exhausted (in Phase 2 there's a single plan, so exhaustion ->
    escalate; Phase 3 will route to a fresh plan and only escalate on the
    second consecutive exhaustion); any budget breached -> escalate. A `flake`
    classification buys a bounded number of free retries that don't burn an
    attempt. Routing itself is pure code -- diagnose records `diagnosis.action`
    and `_route_after_diagnose` reads it."""
    if stop_flag_set(state["run_id"], _loop_state_dir()):
        return {
            "status": "escalated",
            "escalation_reason": "stopped by user",
            "diagnosis": {"action": "escalate"},
        }

    budgets = state["budgets"]
    phase = _failed_phase(state) or "self_check"
    signature, detail = _signature_and_detail(state, phase)
    prev_signature = state.get("failure_signature")  # last attempt's, if any
    category, insight = _diagnose_llm(state, phase, detail)

    no_progress = prev_signature is not None and signature == prev_signature

    # Flake: a bounded free retry that doesn't burn an attempt -- but never for
    # a no-progress repeat (an identical failure twice isn't flakiness).
    flake_free_retries = state.get("flake_free_retries", 0)
    if category == "flake" and not no_progress and flake_free_retries < _MAX_FLAKE_FREE_RETRIES:
        lessons = _append_lesson(state, state.get("attempt", 0), state.get("active_plan_id", "plan-1"),
                                 signature, category, f"[flake, free retry] {insight}")
        return {
            "status": "coding",
            "diagnosis": {"action": "retry", "category": category, "signature": signature, "flake": True},
            "failure_signature": signature,
            "prev_failure_signature": prev_signature,
            "flake_free_retries": flake_free_retries + 1,
            "lessons": lessons,
        }

    attempt = state.get("attempt", 0) + 1
    total_attempts = state.get("total_attempts", 0) + 1
    lessons = _append_lesson(state, attempt, state.get("active_plan_id", "plan-1"), signature, category, insight)

    def _escalate(reason: str) -> dict:
        return {
            "status": "escalated",
            "escalation_reason": reason,
            "attempt": attempt,
            "total_attempts": total_attempts,
            "lessons": lessons,
            "failure_signature": signature,
            "prev_failure_signature": prev_signature,
            "diagnosis": {"action": "escalate", "category": category, "signature": signature, "reason": reason},
        }

    elapsed = time.time() - state.get("run_started_at", time.time())
    token_budget = budgets.get("token_budget", 0)
    hard_budget = None
    if elapsed > budgets["wall_clock_s"]:
        hard_budget = "wall_clock"
    elif total_attempts > budgets["max_total_attempts"]:
        hard_budget = "max_total_attempts"
    elif token_budget and state.get("tokens_used", 0) > token_budget:
        # Token budget is a hard stop at this checkpoint, not a warning (§3.4).
        hard_budget = "token_budget"

    # 1-2. No progress: same signature twice -> active plan exhausted. If another
    # candidate plan remains (and no hard budget is breached), switch to it via
    # plan_tot -- the aggregated lessons steer the re-score (GoT). Escalate once
    # two plans have been exhausted (§3.4 exit 2: a third built on the same
    # lessons lands in the same place) or nothing else is left.
    if no_progress:
        exhausted = list(state.get("exhausted_plan_ids", []))
        active = state.get("active_plan_id", "plan-1")
        if active not in exhausted:
            exhausted.append(active)
        remaining = [p for p in (state.get("candidate_plans") or []) if p.get("id") not in exhausted]
        if len(exhausted) >= 2 or not remaining or hard_budget:
            base = _escalate(hard_budget or ("two_plans_exhausted" if len(exhausted) >= 2 else "no_progress"))
            base["exhausted_plan_ids"] = exhausted
            return base
        return {
            "status": "planning",
            "exhausted_plan_ids": exhausted,
            "attempt": 0,  # the fresh plan gets its own per-plan attempt budget
            "total_attempts": total_attempts,
            "lessons": lessons,
            "failure_signature": signature,
            "prev_failure_signature": prev_signature,
            "diagnosis": {"action": "new_plan", "category": category, "signature": signature},
        }

    # 4. Budgets (token budget is a hard stop here when set; 0 means unlimited).
    if hard_budget:
        return _escalate(hard_budget)
    if attempt > budgets["max_attempts_per_plan"]:
        return _escalate("max_attempts_per_plan")

    # Otherwise: the failure changed and there's budget left -> try again.
    return {
        "status": "coding",
        "attempt": attempt,
        "total_attempts": total_attempts,
        "lessons": lessons,
        "failure_signature": signature,
        "prev_failure_signature": prev_signature,
        "diagnosis": {"action": "retry", "category": category, "signature": signature},
    }


def _route_after_diagnose(state: CodingLoopState) -> str:
    action = (state.get("diagnosis") or {}).get("action")
    if action == "escalate":
        return "escalate"
    if action == "new_plan":  # Phase 3 -- plan switching
        return "plan_tot"
    return "code"


##### 15. State Machine Node 9/10: Finalize (Git commit & report writing)
def finalize_node(state: CodingLoopState) -> dict:
    handle = _handle_from_state(state)
    rev = worktree_commit(handle, f"coding-engineer: {state['goal'][:72]}")
    report_path = write_run_report(state, _loop_state_dir(), outcome="done", commit_rev=rev)
    return {"status": "done", "messages": [_status_message("finalize", True, note=f"report: {report_path}")]}


##### 16. State Machine Node 10/10: Escalate (First-class outcome: commits WIP worktree & writes report)
def escalate_node(state: CodingLoopState) -> dict:
    reason = state.get("escalation_reason") or "unknown"
    rev = ""
    if state.get("worktree_dir"):
        handle = _handle_from_state(state)
        rev = worktree_commit(handle, f"coding-engineer: WIP, escalated ({reason})")
    report_path = write_run_report(state, _loop_state_dir(), outcome="escalated", commit_rev=rev)
    return {"status": "escalated", "messages": [_status_message("escalate", False, note=f"{reason}; report: {report_path}")]}