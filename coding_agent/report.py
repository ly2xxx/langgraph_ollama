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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run_dir(state: dict[str, Any], loop_state_dir: Path) -> Path:
    d = Path(loop_state_dir) / "state" / "coding-engineer" / state["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fmt_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(none)"


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
    lines.append("")

    lines.append("## Acceptance criteria")
    lines.append(_fmt_list(spec.get("acceptance_criteria", [])))
    lines.append("")

    lines.append("## Frozen BDD scenarios")
    lines.append(_fmt_list(state.get("feature_paths", [])))
    lines.append("")

    lines.append("## Gate results")
    lines.append(f"- self_check passed: {test_report.get('passed')}")
    lines.append(f"- bdd_gate passed: {bdd_report.get('passed')}")
    lines.append("")

    lines.append("## Lessons")
    if lessons:
        for lesson in lessons:
            lines.append(f"- attempt {lesson.get('attempt')} ({lesson.get('plan_id')}): {lesson.get('insight')}")
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

    report_path = run_dir / "run-report.md"
    report_path.write_text(render_report(state, outcome, commit_rev), encoding="utf-8")

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
