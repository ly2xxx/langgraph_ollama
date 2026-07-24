"""Minimal Streamlit panel for the Coding Engineer agent (coding_agent/).

This is a lightweight entry point -- target/goal inputs, a run button, and
live per-node status -- not the full Phase 4 polish described in
coding_agent/CODING_ENGINEER.md §5 (budgets expander, diff viewer, demo
queries, telemetry wiring). It exists so the agent can be run from the
browser instead of a terminal; see coding_agent/PHASED_PLAN.md for what's
still deferred to full Phase 4.
"""

from pathlib import Path

import streamlit as st

from coding_agent.engine import _loop_state_dir, build_graph, new_run_id, stream_run
from ui.graph_display import render_graph_diagram


@st.cache_resource(show_spinner="Building agent graph...")
def _topology_graph():
    """Uncheckpointed graph instance used only for the topology picture --
    same pattern as app.py's build_chain cache. The actual runs go through
    stream_run -> CodingEngineer().create_graph(), which owns the real
    SqliteSaver-backed instance."""
    return build_graph()

DEFAULT_TARGET = "."
DEFAULT_GOAL = (
    "Move rag_research_chatbot.py and its class into a new rag_agent/ subfolder, "
    "updating any file that imports it."
)


def render_coding_engineer_panel() -> None:
    st.caption(
        "Points a non-stop code/test/BDD loop at a target git repo. Every run happens on its "
        "own branch in an isolated worktree -- nothing here touches your checkout directly "
        "until you review and merge the branch yourself. See coding_agent/CODING_ENGINEER.md "
        "for how the loop works."
    )

    render_graph_diagram(_topology_graph(), "Coding Engineer")

    target_dir = st.text_input(
        "Target directory (a git repo, or a path inside one)",
        value=DEFAULT_TARGET,
        help="'.' targets this repo. Uncommitted changes won't be picked up -- "
        "git worktree checks out from HEAD.",
    )
    goal = st.text_area("Goal", value=DEFAULT_GOAL, height=100)
    hitl = st.checkbox(
        "Pause for approval if the drafted BDD scenarios are ambiguous",
        value=True,
        help="Recommended for targets with little or no existing test coverage -- the drafted "
        "scenarios are otherwise the only thing that would catch a broken change.",
    )

    if not st.button("Run Coding Engineer"):
        return

    run_id = new_run_id()
    st.write(f"**run_id:** `{run_id}`")
    status_box = st.status("Starting run...", expanded=True)
    final_status = None

    try:
        for update in stream_run(run_id, target_dir, goal, hitl=hitl):
            for node_name, node_update in update.items():
                if node_name == "__interrupt__":
                    status_box.write(f"⏸️ **interrupted** — {node_update}")
                    continue
                node_status = node_update.get("status") if isinstance(node_update, dict) else None
                note = ""
                messages = node_update.get("messages") if isinstance(node_update, dict) else None
                if messages:
                    note = f" — {getattr(messages[-1], 'content', '')}"
                status_box.write(f"**{node_name}** (status={node_status}){note}")
                final_status = node_status or final_status
    except Exception as exc:  # noqa: BLE001 -- surface any failure in the UI rather than crashing the app
        status_box.update(label=f"Run failed: {exc}", state="error")
        st.exception(exc)
        return

    ok = final_status == "done"
    status_box.update(label=f"Run finished: {final_status}", state="complete" if ok else "error")

    report_path = Path(_loop_state_dir()) / "state" / "coding-engineer" / run_id / "run-report.md"
    if report_path.exists():
        with st.expander("Run report", expanded=True):
            st.markdown(report_path.read_text())
    else:
        st.warning(f"No report found at {report_path}")
