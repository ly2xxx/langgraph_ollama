"""Streamlit panel for the Coding Engineer agent (coding_agent/).

Phase 4 (CODING_ENGINEER.md §5): the full browser entry point -- target/goal
inputs with demo goals, a budgets + model-override expander, live per-node
streaming wrapped in telemetry, and a finish view with a verdict banner, the
produced diff, and the run report. Finished runs are remembered per session so
switching the demo goal never loses results. Worktrees are deliberately kept
for inspection (not auto-removed); the panel surfaces the branch + worktree
path so the human can review and merge.
"""

import json
import os
from pathlib import Path

import streamlit as st

import telemetry
from coding_agent.engine import (
    CODING_ENGINEER_LABEL,
    _loop_state_dir,
    build_graph,
    new_run_id,
    stream_run,
)
from coding_agent.models import describe_all
from ui.graph_display import render_graph_diagram


@st.cache_resource(show_spinner="Building agent graph...")
def _topology_graph():
    """Uncheckpointed graph instance used only for the topology picture --
    same pattern as app.py's build_chain cache. The actual runs go through
    stream_run -> CodingEngineer().create_graph(), which owns the real
    SqliteSaver-backed instance."""
    return build_graph()


DEMO_GOALS = [
    "Move rag_research_chatbot.py and its class into a new rag_agent/ subfolder, updating any file that imports it.",
    "In coding_agent/sample_target, implement the string-calculator kata so all scenarios in features/calculator.feature pass.",
    "Extract the duplicate model-construction logic in app.py into a single helper and update call sites.",
]

def _target_selector() -> str:
    return st.text_input(
        "Target directory (a git repo, or a path inside one)",
        value=".",
        help="'.' targets this repo. Uncommitted changes won't be picked up -- git worktree checks out from HEAD.",
    ).strip() or "."


def _budgets_and_models() -> tuple[dict, str, str]:
    """Sidebar controls: the §3.2/§3.4 stop rails plus per-run model overrides.
    Model fields default to whatever the env currently resolves to; changing
    one sets the corresponding CODING_AGENT_*_MODEL env var just before the run
    (get_llm reads env at call time, so this takes effect for the run)."""
    resolved = describe_all()
    with st.sidebar.expander("Coding Engineer budgets", expanded=False):
        budgets = {
            "max_attempts_per_plan": st.number_input("Max attempts / plan", 1, 20, 3),
            "max_plans": st.number_input("Max plans (ToT k)", 1, 6, 3),
            "max_total_attempts": st.number_input("Max total attempts", 1, 50, 9),
            "cmd_timeout_s": st.number_input("Per-command timeout (s)", 10, 600, 120),
            "wall_clock_s": st.number_input("Wall-clock budget (s)", 60, 7200, 1800),
            "token_budget": st.number_input("Token budget (0 = unlimited)", 0, 10_000_000, 0, step=1000),
        }
        st.markdown("**Model overrides** (blank = use .env)")
        primary = st.text_input("Primary model", value=resolved["primary"]["model"] or "").strip()
        secondary = st.text_input("Secondary model (judge + reviewer)", value=resolved["secondary"]["model"] or "").strip()
    return budgets, primary, secondary


def _apply_model_overrides(primary: str, secondary: str) -> None:
    if primary:
        os.environ["CODING_AGENT_PRIMARY_MODEL"] = primary
    if secondary:
        os.environ["CODING_AGENT_SECONDARY_MODEL"] = secondary


def _finish_view(run_id: str) -> None:
    """Verdict banner + diff + report for a run, read back from its state.json /
    run-report.md (written by finalize/escalate). Works for the just-finished
    run and for any past run picked from history -- everything is on disk."""
    run_dir = Path(_loop_state_dir()) / "state" / "coding-engineer" / run_id
    state = {}
    state_path = run_dir / "state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    outcome = state.get("outcome") or state.get("status") or "unknown"
    review = (state.get("review_result") or {}).get("verdict")
    if outcome == "done":
        st.success(f"✅ Done — review verdict: {review}" if review else "✅ Done")
    else:
        st.error(f"⚠️ {outcome} — {state.get('escalation_reason', 'see report')} (a human decides what happens next)")

    branch, worktree = state.get("branch"), state.get("worktree_dir")
    if branch:
        st.caption(f"Branch: `{branch}` · Worktree (kept for inspection): `{worktree}`")
    if state.get("tokens_used"):
        st.caption(f"Tokens (best-effort tally): {state['tokens_used']}")

    diff = state.get("last_diff")
    if diff:
        with st.expander("Diff produced on the branch", expanded=False):
            st.code(diff, language="diff")

    report_path = run_dir / "run-report.md"
    if report_path.exists():
        with st.expander("Run report", expanded=True):
            # encoding="utf-8" is required: the report has em-dashes/arrows/emoji
            # and report.py writes utf-8, but Path.read_text() defaults to the
            # platform encoding (cp1252 on Windows) and would raise. Seen live.
            st.markdown(report_path.read_text(encoding="utf-8"))
    else:
        st.warning(f"No report found at {report_path}")


def _remember_run(run_id: str, goal: str) -> None:
    history = st.session_state.setdefault("ce_history", [])
    history.append({"run_id": run_id, "goal": goal})
    st.session_state["ce_selected_run"] = run_id


def _previous_runs_view() -> None:
    """A picker over this session's finished runs. Because the results live on
    disk (state.json / run-report.md), switching the demo goal -- or any other
    widget -- never loses a run: pick it here and its finish view re-renders."""
    history = st.session_state.get("ce_history", [])
    if not history:
        return
    st.divider()
    st.subheader("Previous runs (this session)")
    by_id = {r["run_id"]: r for r in history}
    run_ids = list(by_id)[::-1]  # most recent first
    selected = st.session_state.get("ce_selected_run", run_ids[0])
    idx = run_ids.index(selected) if selected in run_ids else 0
    picked = st.selectbox(
        "View a run",
        run_ids,
        index=idx,
        format_func=lambda rid: f"{by_id[rid]['goal'][:60]}  ·  {rid}",
        key="ce_run_picker",
    )
    _finish_view(picked)


def render_coding_engineer_panel() -> None:
    st.caption(
        "Points a non-stop code/test/BDD loop at a target git repo. Every run happens on its "
        "own branch in an isolated worktree -- nothing here touches your checkout directly "
        "until you review and merge the branch yourself. See coding_agent/CODING_ENGINEER.md "
        "for how the loop works."
    )

    render_graph_diagram(_topology_graph(), "Coding Engineer")
    budgets, primary_override, secondary_override = _budgets_and_models()

    target_dir = _target_selector()
    demo = st.selectbox("Demo goal (optional)", ["— write my own —", *DEMO_GOALS])
    goal = st.text_area("Goal", value="" if demo.startswith("—") else demo, height=100)
    hitl = st.checkbox(
        "Pause for approval if the drafted BDD scenarios are ambiguous",
        value=True,
        help="Recommended for targets with little or no existing test coverage -- the drafted "
        "scenarios are otherwise the only thing that would catch a broken change.",
    )

    resolved = describe_all()
    st.caption(
        f"Models this run: primary `{primary_override or resolved['primary']['model']}` · "
        f"secondary `{secondary_override or resolved['secondary']['model']}` "
        "(override in the sidebar, or set CODING_AGENT_PRIMARY_MODEL / CODING_AGENT_SECONDARY_MODEL in .env)"
    )

    if st.button("Run Coding Engineer", disabled=not goal.strip()):
        _apply_model_overrides(primary_override, secondary_override)
        primary_model = primary_override or resolved["primary"]["model"] or "unknown"

        run_id = new_run_id()
        st.write(f"**run_id:** `{run_id}`")
        status_box = st.status("Starting run...", expanded=True)
        final_status = None
        try:
            with telemetry.track_request(CODING_ENGINEER_LABEL, primary_model, run_id=run_id):
                for update in stream_run(run_id, target_dir, goal, hitl=hitl, budgets=budgets):
                    for node_name, node_update in update.items():
                        if node_name == "__interrupt__":
                            status_box.write(f"⏸️ **interrupted** — {node_update}")
                            continue
                        if isinstance(node_update, dict):
                            node_status = node_update.get("status")
                            p_tok, c_tok = telemetry.extract_token_usage(node_update)
                            if p_tok or c_tok:
                                telemetry.record_tokens(CODING_ENGINEER_LABEL, primary_model, p_tok, c_tok)
                            messages = node_update.get("messages")
                            note = f" — {getattr(messages[-1], 'content', '')}" if messages else ""
                        else:
                            node_status, note = None, ""
                        status_box.write(f"**{node_name}** (status={node_status}){note}")
                        final_status = node_status or final_status
        except Exception as exc:  # noqa: BLE001 -- surface any failure in the UI rather than crashing the app
            status_box.update(label=f"Run failed: {exc}", state="error")
            st.exception(exc)
            return

        status_box.update(
            label=f"Run finished: {final_status}",
            state="complete" if final_status == "done" else "error",
        )
        _remember_run(run_id, goal)

    _previous_runs_view()
