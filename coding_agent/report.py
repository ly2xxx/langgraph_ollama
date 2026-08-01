"""Run-report and state-snapshot writer for the Coding Engineer agent.

Every run — finished or escalated — leaves a human-readable `run-report.md`
and a machine-readable `state.json` under
`.loop/state/coding-engineer/<run_id>/`. This is the loop's "stay the
engineer" artifact (CODING_ENGINEER.md §2): the human reads this, then the
diff, then decides whether to merge. See CODING_ENGINEER.md §3.3 (finalize
/ escalate).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _run_dir(state: dict[str, Any], loop_state_dir: Path) -> Path:
    d = Path(loop_state_dir) / "state" / "coding-engineer" / state["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fmt_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(none)"


def _tail(text: str | None, n: int = 40) -> str:
    if not text:
        return "(empty)"
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def render_report(state: dict[str, Any], outcome: str, commit_rev: str) -> str:
    spec = state.get("spec") or {}
    budgets = state.get("budgets") or {}
    lessons = state.get("lessons") or []
    test_report = state.get("test_report") or {}
    bdd_report = state.get("bdd_report") or {}

    lines: list[str] = []
    lines.append(f"# Coding Engineer run report — {state.get('run_id', '?')}")
    lines.append("")
    lines.append(f"- **Outcome:** {outcome}")
    if state.get("escalation_reason"):
        lines.append(f"- **Escalation reason:** {state['escalation_reason']}")
    lines.append(f"- **Goal:** {state.get('goal', '?')}")
    lines.append(f"- **Target:** {state.get('target_dir', '?')}")
    lines.append(f"- **Branch:** {state.get('branch', '?')}")
    lines.append(f"- **Commit:** {commit_rev or '(nothing to commit)'}")
    lines.append(f"- **Attempts:** {state.get('total_attempts', 0)} (budget: {budgets.get('max_total_attempts', '?')})")
    tokens_used = state.get("tokens_used", 0)
    if tokens_used:
        tb = budgets.get("token_budget", 0)
        lines.append(f"- **Tokens (best-effort):** {tokens_used}" + (f" (budget: {tb})" if tb else ""))
    if state.get("worktree_dir"):
        # Worktrees are kept for inspection (not auto-removed) -- point the human at it.
        lines.append(f"- **Worktree (kept for inspection):** {state.get('worktree_dir')}")
    lines.append("")

    model_info = state.get("model_info") or {}
    if model_info:
        lines.append("## Models")
        for role in ("primary", "secondary"):
            cfg = model_info.get(role) or {}
            lines.append(f"- **{role}:** provider={cfg.get('provider')} model={cfg.get('model')} base_url={cfg.get('base_url')}")
        lines.append("")

    lines.append("## Acceptance criteria")
    lines.append(_fmt_list(spec.get("acceptance_criteria", [])))
    lines.append("")

    lines.append("## Frozen BDD scenarios")
    lines.append(_fmt_list(state.get("feature_paths", [])))
    lines.append("")

    plans = state.get("candidate_plans") or []
    if plans:
        lines.append("## Plans (ToT)")
        active = state.get("active_plan_id")
        for p in plans:
            marker = " ← active" if p.get("id") == active else ""
            lines.append(f"- **{p.get('id')}** [{p.get('status')}] score={p.get('score')}{marker}: {p.get('rationale', '')}")
        lines.append("")

    lines.append("## Gate results")
    lines.append(f"- self_check passed: {test_report.get('passed')}")
    lines.append(f"- bdd_gate passed: {bdd_report.get('passed')}")
    review = state.get("review_result") or {}
    if review:
        lines.append(f"- review verdict: {review.get('verdict')}")
    lines.append("")

    findings = review.get("findings") or []
    if findings:
        lines.append("## Review findings")
        for f in findings:
            lines.append(f"- **{f.get('severity')}** {f.get('location')}: {f.get('rationale')}")
            if f.get("suggested_fix"):
                lines.append(f"  - fix: {f.get('suggested_fix')}")
        lines.append("")

    # Added after the first live run: a boolean pass/fail plus a one-line
    # lesson summary wasn't enough to diagnose *why* a gate failed without
    # re-running it by hand. Last 40 lines of each command's actual output,
    # only for gates that ran and didn't pass -- kept out of successful runs
    # so the report doesn't balloon on the common path.
    ruff = test_report.get("ruff") or {}
    pytest_self_check = test_report.get("pytest") or {}
    if test_report and not test_report.get("passed"):
        lines.append("## self_check output")
        if ruff.get("returncode") not in (0, None):
            lines.append(f"**ruff** (returncode={ruff.get('returncode')}):")
            lines.append("```")
            lines.append(_tail(ruff.get("stdout")) + (("\n" + _tail(ruff.get("stderr"))) if ruff.get("stderr") else ""))
            lines.append("```")
        if pytest_self_check.get("returncode") not in (0, 5, None):
            lines.append(f"**pytest** (returncode={pytest_self_check.get('returncode')}):")
            lines.append("```")
            lines.append(_tail(pytest_self_check.get("stdout")))
            lines.append("```")
        lines.append("")

    if bdd_report and not bdd_report.get("passed"):
        lines.append("## bdd_gate output")
        lines.append(f"**pytest** (returncode={bdd_report.get('returncode')}):")
        lines.append("```")
        lines.append(_tail(bdd_report.get("stdout")))
        lines.append("```")
        lines.append("")

    lines.append("## Lessons")
    if lessons:
        for lesson in lessons:
            sig = lesson.get("failure_signature")
            sig_short = f" [{sig[:8]}]" if sig else ""
            cat = lesson.get("category")
            cat_tag = f" ({cat})" if cat else ""
            lines.append(
                f"- attempt {lesson.get('attempt')} ({lesson.get('plan_id')}){cat_tag}{sig_short}: "
                f"{lesson.get('insight')}"
            )
        # A repeated signature is *why* a run stops early on no-progress -- make
        # that visible so a human reading the report can see the stall, not just
        # the escalation reason (CODING_ENGINEER.md §3.4).
        sigs = [ls.get("failure_signature") for ls in lessons if ls.get("failure_signature")]
        if len(sigs) >= 2 and sigs[-1] == sigs[-2]:
            lines.append("")
            lines.append(f"> No-progress: the same failure signature `{sigs[-1][:8]}` occurred twice in a row.")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Diff")
    lines.append("```diff")
    lines.append((state.get("last_diff") or "").rstrip("\n"))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def write_run_report(state: dict[str, Any], loop_state_dir: Path, outcome: str, commit_rev: str = "") -> Path:
    run_dir = _run_dir(state, loop_state_dir)

    report_content = render_report(state, outcome, commit_rev)
    report_path = run_dir / "run-report.md"
    report_path.write_text(report_content, encoding="utf-8")

    logger.info(
        "Coding Engineer run report — %s (outcome=%s, branch=%s):\n%s",
        state.get("run_id", "?"),
        outcome,
        state.get("branch", "?"),
        report_content,
    )

    snapshot = dict(state)
    snapshot.pop("messages", None)  # LangChain message objects aren't trivially JSON-serialisable
    snapshot["outcome"] = outcome
    snapshot["commit_rev"] = commit_rev
    snapshot["written_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "state.json").write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")

    return report_path


def stop_flag_path(run_id: str, loop_state_dir: Path) -> Path:
    return Path(loop_state_dir) / "state" / "coding-engineer" / run_id / "STOP"


def stop_flag_set(run_id: str, loop_state_dir: Path) -> bool:
    return stop_flag_path(run_id, loop_state_dir).exists()
