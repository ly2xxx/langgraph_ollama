

Task: Refactor `coding_agent/engine.py` (~1,350 lines) into clean, single-responsibility submodules inside `coding_agent/` while maintaining 100% backward compatibility.

### Objectives & Target Structure

Decompose `coding_agent/engine.py` into the following submodules:

1. `coding_agent/state.py`:

   - `CodingLoopState`, `Budgets`, `Plan`, `Lesson` TypedDict definitions.
   - `DEFAULT_BUDGETS`, `CODING_ENGINEER_LABEL`, and helper functions like `_loop_state_dir`, `_status_message`, `_handle_from_state`.
2. `coding_agent/llm_boundaries.py`:

   - All isolated LLM invocation wrappers: `_llm_parse_target_spec`, `_llm_author_bdd`, `_llm_propose_plans`, `_llm_judge_plans`, `_llm_diagnose`, `_llm_review`, `_run_maker`.
3. `coding_agent/gates.py`:

   - Quality gate logic and differential linting: `_run_ruff_json`, `_ruff_new_findings`, `_render_ruff_findings`, `_read_json_report`, `_read_failures`, `_read_step_defs`, `_harness_exclude_dirs`, `_is_under_any`.
4. `coding_agent/maker_tools.py`:

   - Tool construction: `_build_maker_tools` and `_maker_task_text`.
5. `coding_agent/nodes.py`:

   - StateGraph node implementations (`intake_node`, `author_bdd_node`, `plan_tot_node`, `code_node`, `self_check_node`, `bdd_gate_node`, `review_node`, `diagnose_node`, `finalize_node`, `escalate_node`).
   - Conditional routing functions (`_route_after_intake`, `_route_after_author_bdd`, `_route_after_self_check`, `_route_after_bdd_gate`, `_route_after_review`, `_route_after_diagnose`).
6. `coding_agent/engine.py` (Main Entrypoint & Compatibility Layer):

   - Retain `build_graph()`, `CodingEngineer`, `stream_run()`, `run_cli()`, `new_run_id()`, and `__main__`.
   - Re-export all imported symbols, node functions, boundary functions, and types from the new submodules so that existing imports across `app.py`, `ui/`, and `tests/test_engine.py` continue to work seamlessly without breaking.

### Strict Constraints

1. **Verification First**: Before making any changes, run `pytest coding_agent/tests/` to verify the baseline test suite passes.
2. **Zero Functional Changes**: Do NOT change node names, state keys, prompt formats, routing logic, or graph execution order.
3. **Preserve Monkeypatch Surfaces**: `test_engine.py` monkeypatches functions like `_llm_parse_target_spec`, `_llm_author_bdd`, `_run_maker`, etc. Make sure these remain importable/patchable via `coding_agent.engine` or are updated cleanly in tests if needed.
4. **Final Verification**: Run `pytest coding_agent/tests/` after refactoring. All tests must pass 100%.

# Coding Engineer run report — 20260805T092529-8a049b03

- **Outcome:** done
- **Goal:** Task: Refactor `coding_agent/engine.py` (~1,350 lines) into clean, single-responsibility submodules inside `coding_agent/` while maintaining 100% backward compatibility.

### Objectives & Target Structure

Decompose `coding_agent/engine.py` into the following submodules:

1. `coding_agent/state.py`:

   - `CodingLoopState`, `Budgets`, `Plan`, `Lesson` TypedDict definitions.
   - `DEFAULT_BUDGETS`, `CODING_ENGINEER_LABEL`, and helper functions like `_loop_state_dir`, `_status_message`, `_handle_from_state`.
2. `coding_agent/llm_boundaries.py`:

   - All isolated LLM invocation wrappers: `_llm_parse_target_spec`, `_llm_author_bdd`, `_llm_propose_plans`, `_llm_judge_plans`, `_llm_diagnose`, `_llm_review`, `_run_maker`.
3. `coding_agent/gates.py`:

   - Quality gate logic and differential linting: `_run_ruff_json`, `_ruff_new_findings`, `_render_ruff_findings`, `_read_json_report`, `_read_failures`, `_read_step_defs`, `_harness_exclude_dirs`, `_is_under_any`.
4. `coding_agent/maker_tools.py`:

   - Tool construction: `_build_maker_tools` and `_maker_task_text`.
5. `coding_agent/nodes.py`:

   - StateGraph node implementations (`intake_node`, `author_bdd_node`, `plan_tot_node`, `code_node`, `self_check_node`, `bdd_gate_node`, `review_node`, `diagnose_node`, `finalize_node`, `escalate_node`).
   - Conditional routing functions (`_route_after_intake`, `_route_after_author_bdd`, `_route_after_self_check`, `_route_after_bdd_gate`, `_route_after_review`, `_route_after_diagnose`).
6. `coding_agent/engine.py` (Main Entrypoint & Compatibility Layer):

   - Retain `build_graph()`, `CodingEngineer`, `stream_run()`, `run_cli()`, `new_run_id()`, and `__main__`.
   - Re-export all imported symbols, node functions, boundary functions, and types from the new submodules so that existing imports across `app.py`, `ui/`, and `tests/test_engine.py` continue to work seamlessly without breaking.

### Strict Constraints

1. **Verification First**: Before making any changes, run `pytest coding_agent/tests/` to verify the baseline test suite passes.
2. **Zero Functional Changes**: Do NOT change node names, state keys, prompt formats, routing logic, or graph execution order.
3. **Preserve Monkeypatch Surfaces**: `test_engine.py` monkeypatches functions like `_llm_parse_target_spec`, `_llm_author_bdd`, `_run_maker`, etc. Make sure these remain importable/patchable via `coding_agent.engine` or are updated cleanly in tests if needed.
4. **Final Verification**: Run `pytest coding_agent/tests/` after refactoring. All tests must pass 100%.

- **Target:** H:\code\yl\langgraph_ollama
- **Branch:** coding-engineer/20260805T092529-8a049b03
- **Commit:** 39fbe5a70a9bf3f52189a007f055259714fb04c3
- **Attempts:** 0 (budget: 9)
- **Worktree (kept for inspection):** .loop\worktrees\20260805T092529-8a049b03

## Models

- **primary:** provider=ollama model=glm-5.2:cloud base_url=http://localhost:11434
- **secondary:** provider=ollama model=qwen3-coder:480b-cloud base_url=http://localhost:11434

## Acceptance criteria

- `coding_agent/state.py` exists and contains `CodingLoopState`, `Budgets`, `Plan`, `Lesson`, `DEFAULT_BUDGETS`, `CODING_ENGINEER_LABEL`, `_loop_state_dir`, `_status_message`, `_handle_from_state`.
- `coding_agent/llm_boundaries.py` exists and contains `_llm_parse_target_spec`, `_llm_author_bdd`, `_llm_propose_plans`, `_llm_judge_plans`, `_llm_diagnose`, `_llm_review`, `_run_maker`.
- `coding_agent/gates.py` exists and contains `_run_ruff_json`, `_ruff_new_findings`, `_render_ruff_findings`, `_read_json_report`, `_read_failures`, `_read_step_defs`, `_harness_exclude_dirs`, `_is_under_any`.
- `coding_agent/maker_tools.py` exists and contains `_build_maker_tools`, `_maker_task_text`.
- `coding_agent/nodes.py` exists and contains `intake_node`, `author_bdd_node`, `plan_tot_node`, `code_node`, `self_check_node`, `bdd_gate_node`, `review_node`, `diagnose_node`, `finalize_node`, `escalate_node`, `_route_after_intake`, `_route_after_author_bdd`, `_route_after_self_check`, `_route_after_bdd_gate`, `_route_after_review`, `_route_after_diagnose`.
- `coding_agent/engine.py` retains `build_graph()`, `CodingEngineer`, `stream_run()`, `run_cli()`, `new_run_id()`, and `__main__`.
- `coding_agent/engine.py` re-exports all symbols from the new submodules so existing imports work seamlessly.
- `pytest coding_agent/tests/` passes 100% before and after refactoring.
- No functional changes are made to node names, state keys, prompt formats, routing logic, or graph execution order.
- Monkeypatch surfaces in `test_engine.py` (e.g., `_llm_parse_target_spec`) remain importable/patchable via `coding_agent.engine` or are updated cleanly in tests.

## Frozen BDD scenarios

- features/rag_agent_move.feature

## Plans (ToT)

- **plan-1** [active] score=3.0 ← active: Risk: a hidden cross-module dependency (e.g., a closure or module-level singleton) breaks imports at an intermediate layer, requiring backtracking.
- **plan-2** [untried] score=2.0: Risk: moving all symbols at once before wiring re-exports creates a window where many imports are broken, making it hard to isolate any single failure.
- **plan-3** [untried] score=1.0: Risk: if the original `engine.py` still defines symbols after cloning, Python may resolve monkeypatches to the local copy rather than the submodule copy, causing silent test failures.

## Gate results

- self_check passed: True
- bdd_gate passed: True
- review verdict: approve

## Lessons

(none)

## Diff

```diff
diff --git a/coding_agent/engine.py b/coding_agent/engine.py
index 8471e79..d51399b 100644
--- a/coding_agent/engine.py
+++ b/coding_agent/engine.py
@@ -1,5 +1,22 @@
 """Coding Engineer â€” the non-stop coding agent's LangGraph graph.
 
+This module is the main entrypoint and backward-compatibility layer after
+the single-responsibility refactor.  The implementation now lives in focused
+submodules under ``coding_agent/``:
+
+- ``coding_agent/state.py``        â€” state schema, budgets, small helpers.
+- ``coding_agent/llm_boundaries.py``â€” isolated LLM invocation wrappers.
+- ``coding_agent/gates.py``        â€” quality-gate logic and differential linting.
+- ``coding_agent/maker_tools.py``  â€” maker tool construction and task text.
+- ``coding_agent/nodes.py``        â€” StateGraph node implementations + routing.
+
+Everything that used to be importable from ``coding_agent.engine`` is still
+importable from here (re-exported below), so existing imports across
+``app.py``, ``ui/``, and ``tests/test_engine.py`` keep working unchanged --
+including the monkeypatch surfaces tests rely on (``_llm_parse_target_spec``,
+``_llm_author_bdd``, ``_run_maker``, ``_llm_propose_plans``, ``_llm_judge_plans``,
+``_llm_review``, ``_llm_diagnose``, ``get_llm``, etc.).
+
 Phase 1 scope (CODING_ENGINEER.md Â§6): the linear loop â€”
 intake -> author_bdd -> plan_tot (single fixed plan) -> code -> self_check
 -> bdd_gate -> finalize, with a diagnose stub that retries on failure up to
@@ -10,47 +27,21 @@ signature-based no-progress detection (Phase 2), no adversarial reviewer
 Every LLM call goes through a small boundary function (`_llm_parse_target_spec`,
 `_llm_author_bdd`, `_run_maker`) so tests can monkeypatch just the model call
 and exercise the real graph, worktree, gates, and report writer around it.
-
-Phase 1 follow-up (see PHASED_PLAN.md): the maker's tool surface now
-includes delete_file/move_file (not just write_file), and self_check/bdd_gate
-exclude coding_agent/ from their own scope when present in the target --
-both added once a real refactor-shaped goal (relocating a module to a
-subfolder within this repo) showed the Phase 1-as-shipped surface wasn't
-quite enough for that shape of task.
 """
 
 from __future__ import annotations
 
 import argparse
-import json
-import os
 import sqlite3
-import time
 import uuid
 from datetime import datetime
 from pathlib import Path
-from typing import Annotated, Any, TypedDict
 
-from langchain.agents import AgentExecutor, create_tool_calling_agent
-from langchain_core.messages import AIMessage, HumanMessage
-from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
-from langchain_core.tools import tool
 from langgraph.checkpoint.sqlite import SqliteSaver
 from langgraph.graph import END, StateGraph
-from langgraph.graph.message import add_messages
-from langgraph.types import interrupt
 
-from coding_agent.models import describe_all, get_llm
 import telemetry
-from coding_agent.prompts import (
-    AUTHOR_BDD_PROMPT,
-    DIAGNOSE_PROMPT,
-    INTAKE_PROMPT,
-    MAKER_SYSTEM_PROMPT,
-    PLAN_JUDGE_PROMPT,
-    PLAN_PROPOSE_PROMPT,
-    REVIEW_PROMPT,
-)
+from coding_agent.models import describe_all, get_llm
 from coding_agent.report import stop_flag_set, write_run_report
 from coding_agent.schemas import (
     BddAuthorResult,
@@ -68,15 +59,6 @@ from coding_agent.signatures import (
     template_message,
 )
 from coding_agent.structured import StructuredOutputError, invoke_structured
-
-try:
-    # telemetry lives at the repo root; it's optional and degrades to no-ops.
-    # Used here only for its pure token-usage extractor (no OTel import), so a
-    # token tally can ride in graph state and feed the Â§3.4 token budget.
-    from telemetry import extract_token_usage as _extract_token_usage
-except Exception:  # noqa: BLE001 -- telemetry is optional; never let its absence break the engine
-    def _extract_token_usage(_graph_output) -> tuple[int, int]:
-        return 0, 0
 from coding_agent.tools.code_exec import Jail, JailViolation, run_command
 from coding_agent.tools.worktree import WorktreeHandle, create_worktree
 from coding_agent.tools.worktree import changed_files as worktree_changed_files
@@ -85,1137 +67,74 @@ from coding_agent.tools.worktree import diff as worktree_diff
 from coding_agent.tools.worktree import file_at_baseline as worktree_file_at_baseline
 from coding_agent.tools.worktree import renamed_paths as worktree_renamed_paths
 
-# Display/telemetry label for this agent. Defined here (not in app.py) so the
-# panel can import it without a circular dependency on app.py.
-CODING_ENGINEER_LABEL = "Coding Engineer"
-
-DEFAULT_BUDGETS: dict[str, int] = {
-    "max_attempts_per_plan": 3,
-    "max_plans": 3,
-    "max_total_attempts": 9,
-    "cmd_timeout_s": 120,
-    "wall_clock_s": 1800,
-    "token_budget": 0,
-}
-
-
-# ---------------------------------------------------------------------------
-# State schema (CODING_ENGINEER.md Â§3.2)
-#
-# Three fields were added during Phase 1 implementation that the original
-# plan didn't spell out a home for; see PHASED_PLAN.md "Deviations":
-#   - escalation_reason: escalate's reason needs to travel through state.
-#   - run_started_at: wall-clock budget needs a start time to compare against.
-#   - is_fallback_copy: finalize/escalate need to reconstruct a WorktreeHandle
-#     to commit/diff, and that dataclass field has to come from somewhere.
-# ---------------------------------------------------------------------------
-
-
-class Budgets(TypedDict):
-    max_attempts_per_plan: int
-    max_plans: int
-    max_total_attempts: int
-    cmd_timeout_s: int
-    wall_clock_s: int
-    token_budget: int
-
-
-class Plan(TypedDict):
-    id: str
-    steps: list[str]
-    rationale: str
-    score: float
-    status: str
-
-
-class Lesson(TypedDict):
-    attempt: int
-    plan_id: str
-    failure_signature: str | None
-    category: str | None  # added Phase 2 -- diagnose's LLM classification
-    insight: str
-
-
-class CodingLoopState(TypedDict, total=False):
-    # immutable per run
-    run_id: str
-    target_dir: str
-    worktree_dir: str
-    branch: str
-    is_fallback_copy: bool  # added in Phase 1 -- see module docstring
-    goal: str
-    budgets: Budgets
-    model_info: dict  # added in Phase 1 follow-up -- models.describe_all(), for the report/UI
-    # goal definition
-    spec: dict
-    feature_paths: list[str]
-    hitl_bdd_approval: bool
-    # planning
-    candidate_plans: list[Plan]
-    active_plan_id: str
-    lessons: list[Lesson]
-    # iteration
-    attempt: int
-    total_attempts: int
-    tokens_used: int  # Phase 4 -- best-effort running tally for the token budget (Â§3.4)
-    run_started_at: float  # added in Phase 1 -- see module docstring
-    last_diff: str
-    test_report: dict
-    bdd_report: dict
-    review_result: dict | None  # renamed from `review` -- can't share a name with the review node
-    escalation_reason: str | None  # added in Phase 1 -- see module docstring
-    # no-progress detection (Phase 2 -- CODING_ENGINEER.md Â§3.4)
-    failure_signature: str | None  # this attempt's signature
-    prev_failure_signature: str | None  # last attempt's, for the "same twice" check
-    exhausted_plan_ids: list[str]  # plans killed by no-progress
-    flake_free_retries: int  # free retries already spent on `flake` classifications
-    diagnosis: dict | None  # diagnose's per-attempt verdict incl. the routing action
-    # outcome + UI
-    status: str
-    messages: Annotated[list, add_messages]
-
-
-# ---------------------------------------------------------------------------
-# small helpers
-# ---------------------------------------------------------------------------
-
-
-def _loop_state_dir() -> Path:
-    return Path(os.getenv("CODING_AGENT_LOOP_DIR", ".loop"))
-
-
-def _status_message(node: str, ok: bool, note: str = "") -> AIMessage:
-    tag = "OK" if ok else "FAIL"
-    content = f"[{node}] {tag}" + (f" â€” {note}" if note else "")
-    return AIMessage(content=content, name=node)
-
-
-def _handle_from_state(state: CodingLoopState) -> WorktreeHandle:
-    return WorktreeHandle(
-        target_dir=Path(state["target_dir"]),
-        worktree_dir=Path(state["worktree_dir"]),
-        branch=state["branch"],
-        is_fallback_copy=state.get("is_fallback_copy", False),
-    )
-
-
-def _read_json_report(path: Path) -> dict:
-    if not path.exists():
-        return {}
-    try:
-        data = json.loads(path.read_text(encoding="utf-8"))
-    except (OSError, json.JSONDecodeError):
-        return {}
-    return data.get("summary", {})
-
-
-def _read_failures(path: Path) -> list[dict]:
-    """Failing tests from a pytest-json-report file, normalised for signing
-    (nodeid, error_class, message, top_frame_func) -- see signatures.py.
-    Kept separate from _read_json_report (which returns only the summary, the
-    Phase 1 shape) so the summary contract stays unchanged; diagnose (Phase 2)
-    reads these to compute the failure_signature (Â§3.4)."""
-    if not path.exists():
-        return []
-    try:
-        data = json.loads(path.read_text(encoding="utf-8"))
-    except (OSError, json.JSONDecodeError):
-        return []
-    return extract_failures(data)
-
-
-def _read_step_defs(state: CodingLoopState) -> str:
-    """Concatenate the step-definition files under the frozen feature dirs, for
-    the reviewer to audit for trivial-pass hacks (CODING_ENGINEER.md Â§3.3). The
-    maker wrote these under a frozen .feature file, so they're the likeliest
-    place a green run is actually cheating."""
-    worktree_dir = Path(state["worktree_dir"])
-    feature_dirs = {Path(fp).parent for fp in state.get("feature_paths", [])}
-    chunks: list[str] = []
-    for d in feature_dirs:
-        base = worktree_dir / d
-        if not base.exists():
-            continue
-        for py in sorted(base.rglob("*.py")):
-            try:
-                chunks.append(f"# {py.relative_to(worktree_dir)}\n{py.read_text(encoding='utf-8')}")
-            except OSError:
-                continue
-    return "\n\n".join(chunks) or "(no step definitions found)"
-
-
-def _summarize_failure(state: CodingLoopState) -> str:
-    """Pure-code, no-LLM failure summary for the Phase 1 lesson log.
-
-    Phase 2 (CODING_ENGINEER.md Â§3.4) replaces this with an LLM-classified,
-    normalised failure_signature; this stub keeps the state shape (lessons
-    with an `insight` string) stable across that upgrade.
-    """
-    test_report = state.get("test_report") or {}
-    bdd_report = state.get("bdd_report") or {}
-    if not test_report.get("passed", True):
-        return (
-            f"self_check failed â€” ruff rc={test_report.get('ruff', {}).get('returncode')}, "
-            f"pytest rc={test_report.get('pytest', {}).get('returncode')}, "
-            f"summary={test_report.get('pytest', {}).get('summary')}"
-        )
-    if not bdd_report.get("passed", True):
-        return f"bdd_gate failed â€” pytest rc={bdd_report.get('returncode')}, summary={bdd_report.get('summary')}"
-    return "unknown failure (neither self_check nor bdd_report marked failed)"
-
-
-# ---------------------------------------------------------------------------
-# LLM call boundaries -- monkeypatch these in tests to avoid needing a live model
-# ---------------------------------------------------------------------------
-
-
-def _llm_parse_target_spec(llm, goal: str, target_dir: str) -> TargetSpec:
-    prompt = INTAKE_PROMPT.format(goal=goal, target_dir=target_dir)
-    return invoke_structured(llm, TargetSpec, prompt)
-
-
-def _llm_author_bdd(llm, state: CodingLoopState) -> BddAuthorResult:
-    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
-    prompt = AUTHOR_BDD_PROMPT.format(
-        goal=state["goal"],
-        acceptance_criteria="\n".join(f"- {c}" for c in criteria) or "(none extracted)",
-    )
-    return invoke_structured(llm, BddAuthorResult, prompt)
-
-
-def _llm_diagnose(llm, state: CodingLoopState, phase: str, failure_detail: str) -> DiagnosisResult:
-    lessons = state.get("lessons") or []
-    lesson_lines = (
-        "\n".join(f"- attempt {ls.get('attempt')}: {ls.get('insight')}" for ls in lessons[-5:])
-        or "(none yet)"
-    )
-    prompt = DIAGNOSE_PROMPT.format(
-        goal=state["goal"], phase=phase, failure_detail=failure_detail, lessons=lesson_lines
-    )
-    return invoke_structured(llm, DiagnosisResult, prompt)
-
-
-def _lessons_block(state: CodingLoopState) -> str:
-    """Aggregated lessons for the ToT re-planning prompt (the GoT step) -- empty
-    on the first planning pass, populated once plans start dying."""
-    lessons = state.get("lessons") or []
-    if not lessons:
-        return ""
-    body = "\n".join(f"- ({ls.get('category')}) {ls.get('insight')}" for ls in lessons[-8:])
-    return f"\nLessons from earlier failed attempts (avoid repeating these):\n{body}\n"
-
-
-def _criteria_text(state: CodingLoopState) -> str:
-    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
-    return "\n".join(f"- {c}" for c in criteria) or "(none extracted)"
-
-
-def _llm_propose_plans(llm, state: CodingLoopState, k: int) -> PlanProposal:
-    prompt = PLAN_PROPOSE_PROMPT.format(
-        k=k, goal=state["goal"], acceptance_criteria=_criteria_text(state), lessons_block=_lessons_block(state)
-    )
-    return invoke_structured(llm, PlanProposal, prompt)
-
-
-def _llm_judge_plans(llm, state: CodingLoopState, plans: list[dict]) -> PlanJudgement:
-    plans_block = "\n".join(
-        f"[{i}] {p.get('rationale', '')}\n" + "\n".join(f"    - {s}" for s in p.get("steps", []))
-        for i, p in enumerate(plans)
-    )
-    prompt = PLAN_JUDGE_PROMPT.format(
-        goal=state["goal"],
-        acceptance_criteria=_criteria_text(state),
-        lessons_block=_lessons_block(state),
-        plans_block=plans_block,
-    )
-    return invoke_structured(llm, PlanJudgement, prompt)
-
-
-def _llm_review(llm, state: CodingLoopState) -> ReviewVerdict:
-    bdd = state.get("bdd_report") or {}
-    step_defs = _read_step_defs(state)
-    prompt = REVIEW_PROMPT.format(
-        goal=state["goal"],
-        acceptance_criteria=_criteria_text(state),
-        diff=(state.get("last_diff") or "(no diff)")[:6000],
-        step_defs=step_defs[:6000],
-        test_output=(bdd.get("stdout") or "(no output)")[:2000],
-    )
-    return invoke_structured(llm, ReviewVerdict, prompt)
-
-
-def _build_maker_tools(jail: Jail, budgets: Budgets) -> list:
-    """Read/list/write/delete/move plus a scoped pytest runner. `run_command`
-    supports more binaries than are exposed here (e.g. `git`, `ruff`) --
-    self_check/bdd_gate already cover those; the maker doesn't need them
-    directly. delete_file/move_file were added after Phase 1 shipped (see
-    PHASED_PLAN.md "Phase 1 follow-up") once a real refactor-shaped goal
-    (moving a module to a subfolder) showed write-only wasn't enough for a
-    clean move -- the old path would just be left behind as a duplicate."""
-
-    @tool
-    def read_file(path: str) -> str:
-        """Read a text file's contents. `path` is relative to the worktree root."""
-        try:
-            return jail.read_file(path)
-        except (JailViolation, OSError) as exc:
-            return f"ERROR: {exc}"
-
-    @tool
-    def list_dir(path: str = ".") -> str:
-        """List a directory's entries. `path` is relative to the worktree root."""
-        try:
-            return "\n".join(jail.list_dir(path))
-        except (JailViolation, OSError) as exc:
-            return f"ERROR: {exc}"
-
-    @tool
-    def write_file(path: str, content: str) -> str:
-        """Write (create or overwrite) a text file with the given full content.
-        `path` is relative to the worktree root. Refuses frozen BDD feature files."""
-        try:
-            jail.write_file(path, content)
-            return f"wrote {path}"
-        except (JailViolation, OSError) as exc:
-            return f"ERROR: {exc}"
-
-    @tool
-    def delete_file(path: str) -> str:
-        """Delete a file. `path` is relative to the worktree root. Refuses
-        frozen BDD feature files. Use this to remove a file after moving its
-        content elsewhere with write_file -- write_file alone never deletes
-        the original."""
-        try:
-            jail.delete_file(path)
-            return f"deleted {path}"
-        except (JailViolation, OSError) as exc:
-            return f"ERROR: {exc}"
-
-    @tool
-    def move_file(src_path: str, dst_path: str) -> str:
-        """Move/rename a file. Both paths are relative to the worktree root.
-        Refuses the operation if either end is a frozen BDD feature file."""
-        try:
-            jail.move_file(src_path, dst_path)
-            return f"moved {src_path} -> {dst_path}"
-        except (JailViolation, OSError) as exc:
-            return f"ERROR: {exc}"
-
-    @tool
-    def run_pytest(pytest_args: str = "") -> str:
-        """Run pytest inside the worktree to check your work before finishing.
-        `pytest_args` is an optional space-separated string of extra pytest arguments."""
-        # Deliberately not named `args` -- pydantic's function-wrapping internals
-        # (used by @tool's schema inference) reserve that name as a synthetic
-        # field for wrapping Python's own *args, so a real parameter literally
-        # named `args` silently gets renamed to `v__args` in the generated
-        # schema, which the tool-calling model then can't satisfy. Confirmed
-        # live: this was the exact "run_pytest() got an unexpected keyword
-        # argument 'v__args'" failure from the first two live runs.
-        extra = pytest_args.split() if pytest_args else []
-        result = run_command("pytest", ["-q", *extra], cwd=jail.root, timeout_s=budgets["cmd_timeout_s"])
-        return f"returncode={result.returncode}\n{result.stdout}\n{result.stderr}"
-
-    return [read_file, list_dir, write_file, delete_file, move_file, run_pytest]
-
-
-def _maker_task_text(state: CodingLoopState) -> str:
-    spec = state.get("spec") or {}
-    lessons = state.get("lessons") or []
-    lesson_lines = "\n".join(f"- {lesson['insight']}" for lesson in lessons[-3:]) or "(none yet)"
-    criteria = "\n".join(f"- {c}" for c in spec.get("acceptance_criteria", [])) or "(none extracted)"
-    return (
-        f"Goal: {state['goal']}\n\n"
-        f"Acceptance criteria:\n{criteria}\n\n"
-        f"Frozen BDD scenarios (do not edit): {', '.join(state.get('feature_paths', [])) or '(none)'}\n\n"
-        f"Recent lessons from earlier attempts:\n{lesson_lines}\n\n"
-        "Make the smallest change that could make the tests pass. You may read files, "
-        "list directories, write files, delete files, move/rename files, and run pytest "
-        "to check your work. If you move something, delete the original -- write_file "
-        "alone does not remove it."
-    )
-
-
-def _run_maker(llm, jail: Jail, state: CodingLoopState) -> dict[str, Any]:
-    tools = _build_maker_tools(jail, state["budgets"])
-    prompt = ChatPromptTemplate.from_messages(
-        [
-            ("system", MAKER_SYSTEM_PROMPT),
-            MessagesPlaceholder(variable_name="messages"),
-            MessagesPlaceholder(variable_name="agent_scratchpad"),
-        ]
-    )
-    agent = create_tool_calling_agent(llm, tools, prompt)
-    # max_iterations=8 was too tight for a real multi-file change: the first
-    # live self-hosted run ("Agent stopped due to max iterations" on all 4
-    # attempts) needed read+write on rag_research_chatbot.py, a new
-    # rag_agent/__init__.py, delete of the old file, an app.py import edit,
-    # and a run_pytest check -- more tool calls than a genuine refactor-shaped
-    # goal can fit in 8. Raised to a more realistic budget for multi-file work.
-    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=20)
-    task_message = HumanMessage(content=_maker_task_text(state))
-    return executor.invoke({"messages": [task_message]})
-
-
-# ---------------------------------------------------------------------------
-# nodes
-# ---------------------------------------------------------------------------
-
-
-def intake_node(state: CodingLoopState) -> dict:
-    budgets = {**DEFAULT_BUDGETS, **(state.get("budgets") or {})}
-    llm = get_llm("primary")
-    try:
-        spec = _llm_parse_target_spec(llm, state["goal"], state["target_dir"])
-    except StructuredOutputError as exc:
-        # Escalate gracefully (with a report) instead of letting the raw
-        # exception blow up the graph -- the first live run surfaced exactly
-        # this as an unhandled stack trace in the UI. See structured.py.
-        return {
-            "budgets": budgets,
-            "run_started_at": time.time(),
-            "status": "escalated",
-            "escalation_reason": f"intake structured-output failure: {exc}",
-            "messages": [_status_message("intake", False, note=str(exc)[:200])],
-        }
-
-    if not spec.is_suitable:
-        return {
-            "spec": spec.model_dump(),
-            "budgets": budgets,
-            "run_started_at": time.time(),
-            "status": "escalated",
-            "escalation_reason": f"unsuitable goal: {spec.rejection_reason or 'not checkable'}",
-            "messages": [_status_message("intake", False, note=spec.rejection_reason or "goal rejected")],
-        }
-
-    handle = create_worktree(Path(state["target_dir"]), state["run_id"], _loop_state_dir())
-
-    return {
-        "spec": spec.model_dump(),
-        "budgets": budgets,
-        "worktree_dir": str(handle.worktree_dir),
-        "branch": handle.branch,
-        "target_dir": str(handle.target_dir),
-        "is_fallback_copy": handle.is_fallback_copy,
-        "run_started_at": time.time(),
-        "attempt": 0,
-        "total_attempts": 0,
-        "lessons": [],
-        "candidate_plans": [],
-        "feature_paths": [],
-        "status": "planning",
-        "messages": [_status_message("intake", True, note=f"worktree ready at {handle.worktree_dir}")],
-    }
-
-
-def _route_after_intake(state: CodingLoopState) -> str:
-    return "escalate" if state.get("status") == "escalated" else "author_bdd"
-
-
-def _route_after_author_bdd(state: CodingLoopState) -> str:
-    return "escalate" if state.get("status") == "escalated" else "plan_tot"
-
-
-def author_bdd_node(state: CodingLoopState) -> dict:
-    worktree_dir = Path(state["worktree_dir"])
-    # Bug found on the first real self-hosted run: an unscoped rglob picked up
-    # coding_agent/sample_target/features/calculator.feature -- the agent's own
-    # demo fixture -- and froze it as the "definition of done" for an unrelated
-    # goal (moving rag_research_chatbot.py). Same harness-exclusion rule as
-    # self_check/bdd_gate (_harness_exclude_dirs), applied here too now.
-    harness_excludes = set(_harness_exclude_dirs(worktree_dir))
-    existing = sorted(
-        str(p.relative_to(worktree_dir)).replace(os.sep, "/")
-        for p in worktree_dir.rglob("*.feature")
-        if ".git" not in p.parts and not harness_excludes & set(p.relative_to(worktree_dir).parts)
-    )
-
-    if existing:
-        return {
-            "feature_paths": existing,
-            "status": "planning",
-            "messages": [
-                _status_message("author_bdd", True, note=f"adopted existing: {', '.join(existing)}")
-            ],
-        }
-
-    llm = get_llm("primary", temperature=0.3)
-    try:
-        result = _llm_author_bdd(llm, state)
-    except StructuredOutputError as exc:
-        return {
-            "status": "escalated",
-            "escalation_reason": f"author_bdd structured-output failure: {exc}",
-            "messages": [_status_message("author_bdd", False, note=str(exc)[:200])],
-        }
-
-    if state.get("hitl_bdd_approval") and result.ambiguity:
-        payload = interrupt(
-            {
-                "node": "author_bdd",
-                "reason": result.ambiguity_reason,
-                "draft_feature_gherkin": result.feature_gherkin,
-                "draft_feature_relative_path": result.feature_relative_path,
-            }
-        )
-        if isinstance(payload, dict):
-            result.feature_gherkin = payload.get("feature_gherkin", result.feature_gherkin)
-            result.feature_relative_path = payload.get("feature_relative_path", result.feature_relative_path)
-
-    jail = Jail(root=worktree_dir)  # nothing frozen yet -- these are the files being authored
-    jail.write_file(result.feature_relative_path, result.feature_gherkin)
-    jail.write_file(result.step_defs_relative_path, result.step_defs_python)
-
-    return {
-        "feature_paths": [result.feature_relative_path],
-        "status": "planning",
-        "messages": [_status_message("author_bdd", True, note=f"drafted {result.feature_relative_path}")],
-    }
-
-
-def _fallback_plan() -> Plan:
-    return {
-        "id": "plan-1",
-        "steps": ["Implement the goal against the acceptance criteria; iterate using self_check/bdd_gate feedback."],
-        "rationale": "fallback single plan (propose/judge unavailable)",
-        "score": 1.0,
-        "status": "untried",
-    }
-
-
-def _score_plans(state: CodingLoopState, plans: list[Plan], exclude: set[str]) -> list[Plan]:
-    """Judge (secondary role, temperature 0) scores the not-yet-exhausted plans.
-    On re-entry the aggregated lessons ride along in the prompt -- the GoT step,
-    so a plan that would repeat a known dead end scores low. Degrades gracefully:
-    if the judge call fails, keep any existing scores and otherwise fall back to
-    proposal order (first proposed = best)."""
-    to_score = [p for p in plans if p["id"] not in exclude]
-    if not to_score:
-        return plans
-    secondary = get_llm("secondary", temperature=0.0)
-    try:
-        judgement = _llm_judge_plans(secondary, state, to_score)
-        by_index = {s.plan_index: s.score for s in judgement.scores}
-        for i, p in enumerate(to_score):
-            if i in by_index:
-                p["score"] = float(by_index[i])
-    except StructuredOutputError:
-        for i, p in enumerate(to_score):
-            if not p.get("score"):
-                p["score"] = float(len(to_score) - i)
-    return plans
-
-
-def plan_tot_node(state: CodingLoopState) -> dict:
-    """Tree-of-Thought planning (CODING_ENGINEER.md Â§3.6). First entry: the
-    primary model proposes k distinct plans (hot), the secondary-role judge
-    scores them (cold), and the best untried plan becomes active. Re-entry
-    (after diagnose retires a stalled plan): the surviving candidates are
-    RE-SCORED with the aggregated lessons in the prompt -- not regenerated --
-    and the next best untried plan is selected."""
-    budgets = state["budgets"]
-    k = budgets.get("max_plans", 3)
-    exhausted = set(state.get("exhausted_plan_ids") or [])
-    existing = list(state.get("candidate_plans") or [])
-
-    if not existing:
-        primary = get_llm("primary", temperature=0.8)
-        try:
-            proposal = _llm_propose_plans(primary, state, k)
-            existing = [
-                {"id": f"plan-{i + 1}", "steps": list(p.steps), "rationale": p.rationale, "score": 0.0,
-                 "status": "untried"}
-                for i, p in enumerate(proposal.plans)
-            ] or [_fallback_plan()]
-        except StructuredOutputError:
-            existing = [_fallback_plan()]
-
-    existing = _score_plans(state, existing, exclude=exhausted)
-
-    candidates = [p for p in existing if p["id"] not in exhausted]
-    if not candidates:  # defensive -- diagnose escalates before this can happen
-        return {
-            "candidate_plans": existing,
-            "status": "escalated",
-            "escalation_reason": "no_plans_left",
-            "diagnosis": {"action": "escalate"},
-        }
-
-    best = max(candidates, key=lambda p: p.get("score", 0.0))
-    for p in existing:
-        p["status"] = "active" if p["id"] == best["id"] else ("exhausted" if p["id"] in exhausted else "untried")
-
-    return {
-        "candidate_plans": existing,
-        "active_plan_id": best["id"],
-        "status": "coding",
-        "attempt": 0,  # each plan gets its own per-plan attempt budget
-        "messages": [
-            _status_message("plan_tot", True, note=f"selected {best['id']} (score {best.get('score', 0):.1f}) of {len(existing)}")
-        ],
-    }
-
-
-def code_node(state: CodingLoopState) -> dict:
-    jail = Jail(root=Path(state["worktree_dir"]), frozen=frozenset(Path(p) for p in state.get("feature_paths", [])))
-    llm = get_llm("primary", temperature=0.2)
-    maker_result = _run_maker(llm, jail, state)
-
-    handle = _handle_from_state(state)
-    diff_text = worktree_diff(handle)
-
-    summary = maker_result.get("output", "") if isinstance(maker_result, dict) else str(maker_result)
-    # Best-effort token tally: the maker (AgentExecutor) is where the bulk of
-    # tokens go, and its result may carry usage on the final AIMessage. Ollama
-    # often omits usage on tool-calling turns, so this under-counts rather than
-    # over-counts -- the token budget stays a safety valve, not a precise meter.
-    p_tok, c_tok = _extract_token_usage(maker_result if isinstance(maker_result, dict) else {})
-    return {
-        "last_diff": diff_text,
-        "tokens_used": state.get("tokens_used", 0) + p_tok + c_tok,
-        "status": "coding",
-        # A new attempt invalidates any prior review verdict -- clear it so
-        # diagnose (Phase 3) doesn't mistake a stale reject for this attempt's
-        # outcome when a later gate fails first.
-        "review_result": None,
-        "messages": [_status_message("code", True, note=str(summary)[:200])],
-    }
-
-
-def _harness_exclude_dirs(worktree_dir: Path) -> list[str]:
-    """Directories self_check/bdd_gate should never recurse into, regardless
-    of the target's own scope: the agent's own package, when the target
-    happens to be (or contain) this repo -- e.g. when self-hosting the
-    Coding Engineer on its own codebase, a goal about some other file has
-    no business running coding_agent's ~40-test suite as a side effect.
-    Only returned if actually present, so this is a no-op for any other
-    target. Added after Phase 1 shipped -- see PHASED_PLAN.md "Phase 1
-    follow-up"."""
-    return ["coding_agent"] if (worktree_dir / "coding_agent").is_dir() else []
-
-
-def _run_ruff_json(files: list[str], cwd: Path, harness_excludes: list[str], timeout: int):
-    """Run `ruff check --select E9,F --output-format json` on `files`
-    (relative to `cwd`) and return (findings, raw_result). `findings` is the
-    parsed JSON list, or None if ruff's output couldn't be parsed (caller
-    should then fall back to an opaque rc check). Empty list == clean.
-
-    `--select E9,F` (syntax errors + pyflakes) rather than bare `ruff check`:
-    self_check runs against an arbitrary target worktree whose own ruff config
-    we don't control and shouldn't depend on -- an explicit, minimal, always-
-    the-same selection keeps this a fast correctness check, not a style audit.
-
-    `--per-file-ignores __init__.py:F401`: a package __init__.py that re-exports
-    names (`from .mod import Thing`) trips F401 "imported but unused" -- but that
-    IS the file's purpose, and it's a brand-new file with no baseline to forgive
-    it against, so without this exception a maker creating a re-exporting package
-    (exactly what the RAG POC does with rag_agent/__init__.py) would fail
-    self_check on the single most conventional line in Python packaging. Scoped
-    to F401 in __init__.py only; genuine syntax errors and other pyflakes issues
-    there are still caught.
-    """
-    if not files:
-        return [], None
-    result = run_command(
-        "ruff",
-        ["check", *files, "--select", "E9,F", "--per-file-ignores", "__init__.py:F401",
-         "--output-format", "json", *[f"--extend-exclude={d}" for d in harness_excludes]],
-        cwd=cwd,
-        timeout_s=timeout,
-    )
-    if result.timed_out:
-        return None, result
-    try:
-        findings = json.loads(result.stdout) if result.stdout.strip() else []
-    except json.JSONDecodeError:
-        return None, result
-    return findings, result
-
-
-def _ruff_new_findings(worktree_dir: Path, changed: list[str], handle: WorktreeHandle,
-                       harness_excludes: list[str], timeout: int):
-    """E9,F ruff findings the maker *introduced this run* -- current findings
-    on the changed files, minus those already present in each file at the run's
-    baseline (HEAD), compared per (relative-path, rule-code) so line shifts from
-    the edit don't matter. Files the maker newly created have no baseline, so
-    every finding in them counts (a brand-new file should be clean).
-
-    Why this exists: scoping ruff to changed files (previous fix) still gated on
-    pre-existing debt whenever the maker legitimately had to touch a file that
-    already carried it -- the live run escalated 4x because app.py's import line
-    genuinely needed updating for the module move, and app.py already had an
-    unrelated duplicate `import os` (F811). The maker reported "all 6 BDD
-    scenarios pass" every attempt, but self_check blocked before bdd_gate could
-    confirm it. Forgiving pre-existing findings fixes that while still catching
-    anything the maker actually breaks.
-
-    Returns (new_findings, current_result). new_findings is None if ruff output
-    couldn't be parsed at all (caller falls back to opaque rc)."""
-    import tempfile
-    from collections import Counter
-
-    current, current_result = _run_ruff_json(changed, worktree_dir, harness_excludes, timeout)
-    if current is None:
-        return None, current_result
-    if not current:
-        return [], current_result
-
-    # A moved file has no blob at its new path in HEAD; without this its
-    # (pre-existing) content would all read as newly introduced. renamed_paths
-    # lets us look the baseline up at the file's OLD path instead. Written into
-    # tmp under the NEW path so the (relative-path, code) comparison key lines
-    # up with the current findings.
-    renames = worktree_renamed_paths(handle)
-    with tempfile.TemporaryDirectory() as tmp:
-        tmp_path = Path(tmp)
-        baseline_files: list[str] = []
-        for rel in changed:
-            content = worktree_file_at_baseline(handle, rel)
-            if content is None and rel in renames:
-                content = worktree_file_at_baseline(handle, renames[rel])
-            if content is None:
-                continue  # genuinely new file this run -> no baseline; its findings all count
-            dest = tmp_path / rel
-            dest.parent.mkdir(parents=True, exist_ok=True)
-            dest.write_text(content, encoding="utf-8")
-            baseline_files.append(rel)
-        baseline, _ = _run_ruff_json(baseline_files, tmp_path, [], timeout)
-        baseline = baseline or []
-
-    def _key(finding: dict, root: Path) -> tuple[str, str]:
-        fname = finding.get("filename", "")
-        try:
-            rel = os.path.relpath(fname, root)
-        except ValueError:
-            rel = fname
-        return (rel.replace(os.sep, "/"), finding.get("code") or "")
-
-    baseline_counts = Counter(_key(f, tmp_path) for f in baseline)
-    seen: Counter = Counter()
-    new: list[dict] = []
-    for f in current:
-        k = _key(f, worktree_dir)
-        seen[k] += 1
-        if seen[k] > baseline_counts.get(k, 0):
-            new.append(f)
-    return new, current_result
-
-
-def _render_ruff_findings(findings: list[dict]) -> str:
-    """One line per finding for the run report (json output isn't human-facing)."""
-    if not findings:
-        return ""
-    lines = []
-    for f in findings:
-        loc = f.get("location") or {}
-        rel = f.get("filename", "?")
-        lines.append(f"{rel}:{loc.get('row', '?')}:{loc.get('column', '?')} {f.get('code')} {f.get('message', '')}")
-    return "\n".join(lines)
-
-
-def _is_under_any(rel_path: str, dirs: set[str]) -> bool:
-    """True if rel_path lives inside one of `dirs` (or is one of them)."""
-    parts = Path(rel_path).parts
-    for d in dirs:
-        dparts = Path(d).parts
-        if len(parts) >= len(dparts) and tuple(parts[: len(dparts)]) == dparts:
-            return True
-    return False
-
-
-def self_check_node(state: CodingLoopState) -> dict:
-    worktree_dir = Path(state["worktree_dir"])
-    timeout = state["budgets"]["cmd_timeout_s"]
-    harness_excludes = _harness_exclude_dirs(worktree_dir)
-
-    # Scope ruff to files changed this run AND only fail on findings this run
-    # introduced (see _ruff_new_findings for the full why). Two live-run bugs
-    # drove this: (1) an unscoped `ruff check .` failed on pre-existing debt in
-    # files the maker never touched; (2) scoping to changed files still failed
-    # on pre-existing debt in a file the maker legitimately *had* to touch
-    # (app.py's import line). Differential-vs-baseline forgives both.
-    #
-    # Also exclude the frozen BDD harness (the feature dir + its step defs) and
-    # the agent's own package: those aren't the maker's implementation change.
-    # author_bdd *generates* the step-defs file, and it routinely leaves an
-    # unused `import pytest` in it (F401) -- that's bdd_gate's code to run, not
-    # self_check's to lint. The live RAG POC's move actually completed, and the
-    # ONLY thing blocking finalization was self_check flagging F401 in that
-    # generated step-defs file.
-    excluded_dirs = set(harness_excludes) | {
-        str(Path(fp).parent).replace(os.sep, "/") for fp in state.get("feature_paths", [])
-    }
-    handle = _handle_from_state(state)
-    changed = [
-        p
-        for p in worktree_changed_files(handle)
-        if (worktree_dir / p).exists() and p.endswith(".py") and not _is_under_any(p, excluded_dirs)
-    ]
-
-    new_findings, ruff_result = _ruff_new_findings(worktree_dir, changed, handle, harness_excludes, timeout)
-    if new_findings is None:
-        # Couldn't parse ruff's json (or it timed out) -> fall back to an opaque
-        # rc check on the changed files, so a broken ruff invocation fails safe
-        # rather than silently passing.
-        fallback = run_command(
-            "ruff",
-            ["check", *(changed or ["."]), "--select", "E9,F", "--per-file-ignores", "__init__.py:F401",
-             *[f"--extend-exclude={d}" for d in harness_excludes]],
-            cwd=worktree_dir,
-            timeout_s=timeout,
-        )
-        ruff_returncode = fallback.returncode
-        ruff_stdout = fallback.stdout
-        ruff_stderr = fallback.stderr
-        ruff_timed_out = fallback.timed_out
-        ruff_passed = fallback.returncode == 0 and not fallback.timed_out
-    else:
-        ruff_returncode = 1 if new_findings else 0
-        ruff_stdout = _render_ruff_findings(new_findings)
-        ruff_stderr = ruff_result.stderr if ruff_result else ""
-        ruff_timed_out = ruff_result.timed_out if ruff_result else False
-        ruff_passed = not new_findings
-
-    ignore_args: list[str] = []
-    for feature_path in state.get("feature_paths", []):
-        ignore_args.extend(["--ignore", str(Path(feature_path).parent)])
-    for excluded in harness_excludes:
-        ignore_args.extend(["--ignore", excluded])
-
-    report_file = worktree_dir / ".self_check_report.json"
-    pytest_result = run_command(
-        "pytest",
-        ["-q", *ignore_args, "--json-report", f"--json-report-file={report_file.name}"],
-        cwd=worktree_dir,
-        timeout_s=timeout,
-    )
-    summary = _read_json_report(report_file)
-    failures = _read_failures(report_file)
-    report_file.unlink(missing_ok=True)
-
-    # pytest exits 5 when it collects zero tests -- expected when the only
-    # tests in scope ARE the frozen BDD scenarios (self_check ignores them;
-    # bdd_gate is the node responsible for actually finding and running them).
-    pytest_ok = pytest_result.returncode in (0, 5) and not pytest_result.timed_out
-    passed = ruff_passed and pytest_ok
-
-    test_report = {
-        "ruff": {
-            "returncode": ruff_returncode,
-            "stdout": ruff_stdout,
-            "stderr": ruff_stderr,
-            "timed_out": ruff_timed_out,
-        },
-        "pytest": {
-            "returncode": pytest_result.returncode,
-            "stdout": pytest_result.stdout,
-            "stderr": pytest_result.stderr,
-            "timed_out": pytest_result.timed_out,
-            "summary": summary,
-            "failures": failures,  # normalised for signing -- see signatures.py / diagnose
-        },
-        # ruff findings are signable too (a ruff-only self_check failure has no
-        # pytest failure): the sorted rule codes are a stable descriptor.
-        "ruff_codes": sorted({f.get("code") for f in (new_findings or []) if f.get("code")}),
-        "passed": passed,
-    }
-    return {"test_report": test_report, "status": "testing", "messages": [_status_message("self_check", passed)]}
-
-
-def _route_after_self_check(state: CodingLoopState) -> str:
-    return "bdd_gate" if state["test_report"]["passed"] else "diagnose"
-
-
-def bdd_gate_node(state: CodingLoopState) -> dict:
-    worktree_dir = Path(state["worktree_dir"])
-    timeout = state["budgets"]["cmd_timeout_s"]
-    feature_paths = state.get("feature_paths", [])
-    scope_dirs = sorted({str(Path(p).parent) for p in feature_paths}) or ["."]
-    # Defensive, not just belt-and-braces for the common case: scope_dirs
-    # only falls back to "." if feature_paths is somehow empty here, but
-    # when it does, this is what stops that fallback from recursing into
-    # the agent's own harness -- see _harness_exclude_dirs.
-    ignore_args = [arg for excluded in _harness_exclude_dirs(worktree_dir) for arg in ("--ignore", excluded)]
-
-    report_file = worktree_dir / ".bdd_report.json"
-    result = run_command(
-        "pytest",
-        ["-q", *scope_dirs, *ignore_args, "--json-report", f"--json-report-file={report_file.name}"],
-        cwd=worktree_dir,
-        timeout_s=timeout,
-    )
-    summary = _read_json_report(report_file)
-    failures = _read_failures(report_file)
-    report_file.unlink(missing_ok=True)
-
-    passed = result.returncode == 0 and not result.timed_out
-    bdd_report = {
-        "returncode": result.returncode,
-        "stdout": result.stdout,
-        "stderr": result.stderr,
-        "timed_out": result.timed_out,
-        "summary": summary,
-        "failures": failures,  # normalised for signing -- see signatures.py / diagnose
-        "passed": passed,
-    }
-    return {"bdd_report": bdd_report, "status": "testing", "messages": [_status_message("bdd_gate", passed)]}
-
-
-def _route_after_bdd_gate(state: CodingLoopState) -> str:
-    # Phase 3: a green bdd_gate no longer finalizes directly -- the adversarial
-    # reviewer (checker) gets the last word (CODING_ENGINEER.md Â§3.1/Â§3.3).
-    return "review" if state["bdd_report"]["passed"] else "diagnose"
-
-
-def review_node(state: CodingLoopState) -> dict:
-    """Adversarial checker (CODING_ENGINEER.md Â§3.3), always the secondary role
-    (Â§3.5) -- a different model catches more than a different prompt on the same
-    one. Sees the spec, diff, step defs, and (green) test output, NOT the maker's
-    reasoning, and specifically hunts trivial-pass hacks in the step defs.
-    reject requires a blocker/major finding; minor-only downgrades to
-    approve_with_notes (notes land in the report, run still finalizes)."""
-    if stop_flag_set(state["run_id"], _loop_state_dir()):
-        return {"status": "escalated", "escalation_reason": "stopped by user", "diagnosis": {"action": "escalate"}}
-
-    secondary = get_llm("secondary", temperature=0.0)
-    try:
-        verdict = _llm_review(secondary, state)
-    except StructuredOutputError:
-        # A review hiccup must not block an already-green run -> approve with a note.
-        verdict = ReviewVerdict(verdict="approve_with_notes", findings=[])
-
-    blocking = [f for f in verdict.findings if f.severity in ("blocker", "major")]
-    is_reject = verdict.verdict == "reject" and bool(blocking)
-    review = {
-        "verdict": "reject" if is_reject else ("approve_with_notes" if verdict.findings else "approve"),
-        "findings": [f.model_dump() for f in verdict.findings],
-        "blocking": [f.model_dump() for f in blocking],
-    }
-    note = f"{review['verdict']}" + (f" ({len(blocking)} blocking)" if blocking else "")
-    return {"review_result": review, "status": "testing", "messages": [_status_message("review", not is_reject, note=note)]}
-
-
-def _route_after_review(state: CodingLoopState) -> str:
-    review = state.get("review_result") or {}
-    return "diagnose" if review.get("verdict") == "reject" and review.get("blocking") else "finalize"
-
-
-_MAX_FLAKE_FREE_RETRIES = 2  # a genuinely flaky gate shouldn't spin forever on "free" retries
-
-
-def _failed_phase(state: CodingLoopState) -> str | None:
-    """Which gate failed this attempt (closed set, matches Â§3.4's `phase`).
-    A review reject is only 'this attempt's' failure because code_node clears
-    the prior review at the start of every attempt, so a stale reject can't
-    shadow a later self_check/bdd_gate failure."""
-    review = state.get("review_result") or {}
-    if review.get("verdict") == "reject" and review.get("blocking"):
-        return "review"
-    if not (state.get("test_report") or {}).get("passed", True):
-        return "self_check"
-    if not (state.get("bdd_report") or {}).get("passed", True):
-        return "bdd_gate"
-    return None
-
-
-def _signature_and_detail(state: CodingLoopState, phase: str) -> tuple[str, str]:
-    """(failure_signature, human detail) for the failed gate. Prefers the first
-    failing pytest test (the Â§3.4 recipe); falls back to a stable descriptor for
-    a ruff-only self_check failure (sorted rule codes) or an opaque gate error."""
-    if phase == "self_check":
-        report = state.get("test_report") or {}
-        failures = (report.get("pytest") or {}).get("failures") or []
-        if failures:
-            f = failures[0]
-            return signature_for_failure(phase, f), f"{f.get('nodeid')}: {f.get('message')}"
-        codes = report.get("ruff_codes") or []
-        detail = "ruff findings: " + (", ".join(codes) or ((report.get("ruff") or {}).get("stdout") or "")[:400])
-        return compute_signature(phase, "ruff", "ruff", ",".join(sorted(codes)), ""), detail
-    if phase == "review":
-        review = state.get("review_result") or {}
-        blocking = review.get("blocking") or []
-        first = blocking[0] if blocking else {}
-        # A maker/checker stalemate is no-progress by another name (Â§3.4): sign the
-        # rejection by (location, severity) so a reviewer that keeps rejecting the
-        # same spot is caught by the same "same signature twice" rule.
-        sig = review_signature(first.get("location", ""), first.get("severity", ""))
-        detail = "review reject: " + "; ".join(
-            f"{f.get('severity')} {f.get('location')}: {f.get('rationale')}" for f in blocking[:3]
-        )
-        return sig, detail
-    # bdd_gate
-    report = state.get("bdd_report") or {}
-    failures = report.get("failures") or []
-    if failures:
-        f = failures[0]
-        return signature_for_failure(phase, f), f"{f.get('nodeid')}: {f.get('message')}"
-    stdout = report.get("stdout") or ""
-    return compute_signature(phase, "bdd", "bdd", template_message(stdout), ""), f"bdd_gate failed:\n{stdout[:400]}"
-
-
-def _diagnose_llm(state: CodingLoopState, phase: str, detail: str) -> tuple[str, str]:
-    """(category, insight) from the LLM, degrading gracefully: a structured-output
-    hiccup in diagnose must never crash the loop, so on failure we fall back to
-    an 'unknown' category (no free flake retry) and the code-only summary."""
-    try:
-        llm = get_llm("primary", temperature=0.0)
-        result = _llm_diagnose(llm, state, phase, detail)
-        return result.category, (result.insight or _summarize_failure(state))
-    except Exception:  # noqa: BLE001 -- diagnose is best-effort; a model/network hiccup here must not crash the loop
-        return "unknown", _summarize_failure(state)
-
-
-def diagnose_node(state: CodingLoopState) -> dict:
-    """Classify the failure, sign it (Â§3.4), and decide retry / escalate.
-
-    Hard exits, in order (Â§3.4): stop flag; same signature twice in a row ->
-    active plan exhausted (in Phase 2 there's a single plan, so exhaustion ->
-    escalate; Phase 3 will route to a fresh plan and only escalate on the
-    second consecutive exhaustion); any budget breached -> escalate. A `flake`
-    classification buys a bounded number of free retries that don't burn an
-    attempt. Routing itself is pure code -- diagnose records `diagnosis.action`
-    and `_route_after_diagnose` reads it."""
-    if stop_flag_set(state["run_id"], _loop_state_dir()):
-        return {
-            "status": "escalated",
-            "escalation_reason": "stopped by user",
-            "diagnosis": {"action": "escalate"},
-        }
-
-    budgets = state["budgets"]
-    phase = _failed_phase(state) or "self_check"
-    signature, detail = _signature_and_detail(state, phase)
-    prev_signature = state.get("failure_signature")  # last attempt's, if any
-    category, insight = _diagnose_llm(state, phase, detail)
-
-    no_progress = prev_signature is not None and signature == prev_signature
-
-    # Flake: a bounded free retry that doesn't burn an attempt -- but never for
-    # a no-progress repeat (an identical failure twice isn't flakiness).
-    flake_free_retries = state.get("flake_free_retries", 0)
-    if category == "flake" and not no_progress and flake_free_retries < _MAX_FLAKE_FREE_RETRIES:
-        lessons = _append_lesson(state, state.get("attempt", 0), state.get("active_plan_id", "plan-1"),
-                                 signature, category, f"[flake, free retry] {insight}")
-        return {
-            "status": "coding",
-            "diagnosis": {"action": "retry", "category": category, "signature": signature, "flake": True},
-            "failure_signature": signature,
-            "prev_failure_signature": prev_signature,
-            "flake_free_retries": flake_free_retries + 1,
-            "lessons": lessons,
-        }
-
-    attempt = state.get("attempt", 0) + 1
-    total_attempts = state.get("total_attempts", 0) + 1
-    lessons = _append_lesson(state, attempt, state.get("active_plan_id", "plan-1"), signature, category, insight)
-
-    def _escalate(reason: str) -> dict:
-        return {
-            "status": "escalated",
-            "escalation_reason": reason,
-            "attempt": attempt,
-            "total_attempts": total_attempts,
-            "lessons": lessons,
-            "failure_signature": signature,
-            "prev_failure_signature": prev_signature,
-            "diagnosis": {"action": "escalate", "category": category, "signature": signature, "reason": reason},
-        }
-
-    elapsed = time.time() - state.get("run_started_at", time.time())
-    token_budget = budgets.get("token_budget", 0)
-    hard_budget = None
-    if elapsed > budgets["wall_clock_s"]:
-        hard_budget = "wall_clock"
-    elif total_attempts > budgets["max_total_attempts"]:
-        hard_budget = "max_total_attempts"
-    elif token_budget and state.get("tokens_used", 0) > token_budget:
-        # Token budget is a hard stop at this checkpoint, not a warning (Â§3.4).
-        hard_budget = "token_budget"
-
-    # 1-2. No progress: same signature twice -> active plan exhausted. If another
-    # candidate plan remains (and no hard budget is breached), switch to it via
-    # plan_tot -- the aggregated lessons steer the re-score (GoT). Escalate once
-    # two plans have been exhausted (Â§3.4 exit 2: a third built on the same
-    # lessons lands in the same place) or nothing else is left.
-    if no_progress:
-        exhausted = list(state.get("exhausted_plan_ids", []))
-        active = state.get("active_plan_id", "plan-1")
-        if active not in exhausted:
-            exhausted.append(active)
-        remaining = [p for p in (state.get("candidate_plans") or []) if p.get("id") not in exhausted]
-        if len(exhausted) >= 2 or not remaining or hard_budget:
-            base = _escalate(hard_budget or ("two_plans_exhausted" if len(exhausted) >= 2 else "no_progress"))
-            base["exhausted_plan_ids"] = exhausted
-            return base
-        return {
-            "status": "planning",
-            "exhausted_plan_ids": exhausted,
-            "attempt": 0,  # the fresh plan gets its own per-plan attempt budget
-            "total_attempts": total_attempts,
-            "lessons": lessons,
-            "failure_signature": signature,
-            "prev_failure_signature": prev_signature,
-            "diagnosis": {"action": "new_plan", "category": category, "signature": signature},
-        }
-
-    # 4. Budgets (token budget is a hard stop here when set; 0 means unlimited).
-    if hard_budget:
-        return _escalate(hard_budget)
-    if attempt > budgets["max_attempts_per_plan"]:
-        return _escalate("max_attempts_per_plan")
-
-    # Otherwise: the failure changed and there's budget left -> try again.
-    return {
-        "status": "coding",
-        "attempt": attempt,
-        "total_attempts": total_attempts,
-        "lessons": lessons,
-        "failure_signature": signature,
-        "prev_failure_signature": prev_signature,
-        "diagnosis": {"action": "retry", "category": category, "signature": signature},
-    }
-
-
-def _append_lesson(state: CodingLoopState, attempt: int, plan_id: str, signature: str,
-                   category: str, insight: str) -> list:
-    lessons = list(state.get("lessons", []))
-    lessons.append(
-        {
-            "attempt": attempt,
-            "plan_id": plan_id,
-            "failure_signature": signature,
-            "category": category,
-            "insight": insight,
-        }
-    )
-    return lessons
-
-
-def _route_after_diagnose(state: CodingLoopState) -> str:
-    action = (state.get("diagnosis") or {}).get("action")
-    if action == "escalate":
-        return "escalate"
-    if action == "new_plan":  # Phase 3 -- plan switching
-        return "plan_tot"
-    return "code"
-
+# -- state.py re-exports ---------------------------------------------------
+from coding_agent.state import (  # noqa: F401
+    CODING_ENGINEER_LABEL,
+    DEFAULT_BUDGETS,
+    Budgets,
+    CodingLoopState,
+    Lesson,
+    Plan,
+    _handle_from_state,
+    _loop_state_dir,
+    _status_message,
+)
 
-def finalize_node(state: CodingLoopState) -> dict:
-    handle = _handle_from_state(state)
-    rev = worktree_commit(handle, f"coding-engineer: {state['goal'][:72]}")
-    report_path = write_run_report(state, _loop_state_dir(), outcome="done", commit_rev=rev)
-    return {"status": "done", "messages": [_status_message("finalize", True, note=f"report: {report_path}")]}
+# -- gates.py re-exports ---------------------------------------------------
+from coding_agent.gates import (  # noqa: F401
+    _harness_exclude_dirs,
+    _is_under_any,
+    _read_failures,
+    _read_json_report,
+    _read_step_defs,
+    _render_ruff_findings,
+    _ruff_new_findings,
+    _run_ruff_json,
+)
 
+# -- maker_tools.py re-exports ---------------------------------------------
+from coding_agent.maker_tools import _build_maker_tools, _maker_task_text  # noqa: F401
+
+# -- llm_boundaries.py re-exports ------------------------------------------
+from coding_agent.llm_boundaries import (  # noqa: F401
+    _criteria_text,
+    _lessons_block,
+    _llm_author_bdd,
+    _llm_diagnose,
+    _llm_judge_plans,
+    _llm_parse_target_spec,
+    _llm_propose_plans,
+    _llm_review,
+    _run_maker,
+)
 
-def escalate_node(state: CodingLoopState) -> dict:
-    reason = state.get("escalation_reason") or "unknown"
-    rev = ""
-    if state.get("worktree_dir"):
-        handle = _handle_from_state(state)
-        rev = worktree_commit(handle, f"coding-engineer: WIP, escalated ({reason})")
-    report_path = write_run_report(state, _loop_state_dir(), outcome="escalated", commit_rev=rev)
-    return {"status": "escalated", "messages": [_status_message("escalate", False, note=f"{reason}; report: {report_path}")]}
+# -- nodes.py re-exports ---------------------------------------------------
+from coding_agent.nodes import (  # noqa: F401
+    _append_lesson,
+    _diagnose_llm,
+    _failed_phase,
+    _fallback_plan,
+    _MAX_FLAKE_FREE_RETRIES,
+    _route_after_author_bdd,
+    _route_after_bdd_gate,
+    _route_after_diagnose,
+    _route_after_intake,
+    _route_after_review,
+    _route_after_self_check,
+    _score_plans,
+    _signature_and_detail,
+    _summarize_failure,
+    author_bdd_node,
+    bdd_gate_node,
+    code_node,
+    diagnose_node,
+    escalate_node,
+    finalize_node,
+    intake_node,
+    plan_tot_node,
+    review_node,
+    self_check_node,
+)
 
 
 # ---------------------------------------------------------------------------
@@ -1345,4 +264,4 @@ if __name__ == "__main__":
     parser.add_argument("--hitl", action="store_true", help="Enable the optional author_bdd HITL pause.")
     args = parser.parse_args()
 
-    run_cli(args.target, args.goal, hitl=args.hitl)
+    run_cli(args.target, args.goal, hitl=args.hitl)
\ No newline at end of file
diff --git a/coding_agent/gates.py b/coding_agent/gates.py
new file mode 100644
index 0000000..a33d423
--- /dev/null
+++ b/coding_agent/gates.py
@@ -0,0 +1,207 @@
+"""Quality-gate logic and differential linting for the Coding Engineer loop.
+
+Extracted from ``coding_agent/engine.py`` during the single-responsibility
+refactor.  Contains the ruff/pytest report readers, the differential
+"new findings" computation, and the harness-exclusion helpers shared by
+self_check / bdd_gate / author_bdd.
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import tempfile
+from collections import Counter
+from pathlib import Path
+
+from coding_agent.signatures import extract_failures
+from coding_agent.state import CodingLoopState
+from coding_agent.tools.code_exec import run_command
+from coding_agent.tools.worktree import (
+    WorktreeHandle,
+    file_at_baseline as worktree_file_at_baseline,
+    renamed_paths as worktree_renamed_paths,
+)
+
+
+def _read_json_report(path: Path) -> dict:
+    if not path.exists():
+        return {}
+    try:
+        data = json.loads(path.read_text(encoding="utf-8"))
+    except (OSError, json.JSONDecodeError):
+        return {}
+    return data.get("summary", {})
+
+
+def _read_failures(path: Path) -> list[dict]:
+    """Failing tests from a pytest-json-report file, normalised for signing
+    (nodeid, error_class, message, top_frame_func) -- see signatures.py.
+    Kept separate from _read_json_report (which returns only the summary, the
+    Phase 1 shape) so the summary contract stays unchanged; diagnose (Phase 2)
+    reads these to compute the failure_signature (Â§3.4)."""
+    if not path.exists():
+        return []
+    try:
+        data = json.loads(path.read_text(encoding="utf-8"))
+    except (OSError, json.JSONDecodeError):
+        return []
+    return extract_failures(data)
+
+
+def _read_step_defs(state: CodingLoopState) -> str:
+    """Concatenate the step-definition files under the frozen feature dirs, for
+    the reviewer to audit for trivial-pass hacks (CODING_ENGINEER.md Â§3.3). The
+    maker wrote these under a frozen .feature file, so they're the likeliest
+    place a green run is actually cheating."""
+    worktree_dir = Path(state["worktree_dir"])
+    feature_dirs = {Path(fp).parent for fp in state.get("feature_paths", [])}
+    chunks: list[str] = []
+    for d in feature_dirs:
+        base = worktree_dir / d
+        if not base.exists():
+            continue
+        for py in sorted(base.rglob("*.py")):
+            try:
+                chunks.append(f"# {py.relative_to(worktree_dir)}\n{py.read_text(encoding='utf-8')}")
+            except OSError:
+                continue
+    return "\n\n".join(chunks) or "(no step definitions found)"
+
+
+def _harness_exclude_dirs(worktree_dir: Path) -> list[str]:
+    """Directories self_check/bdd_gate should never recurse into, regardless
+    of the target's own scope: the agent's own package, when the target
+    happens to be (or contain) this repo -- e.g. when self-hosting the
+    Coding Engineer on its own codebase, a goal about some other file has
+    no business running coding_agent's ~40-test suite as a side effect.
+    Only returned if actually present, so this is a no-op for any other
+    target. Added after Phase 1 shipped -- see PHASED_PLAN.md "Phase 1
+    follow-up"."""
+    return ["coding_agent"] if (worktree_dir / "coding_agent").is_dir() else []
+
+
+def _run_ruff_json(files: list[str], cwd: Path, harness_excludes: list[str], timeout: int):
+    """Run `ruff check --select E9,F --output-format json` on `files`
+    (relative to `cwd`) and return (findings, raw_result). `findings` is the
+    parsed JSON list, or None if ruff's output couldn't be parsed (caller
+    should then fall back to an opaque rc check). Empty list == clean.
+
+    `--select E9,F` (syntax errors + pyflakes) rather than bare `ruff check`:
+    self_check runs against an arbitrary target worktree whose own ruff config
+    we don't control and shouldn't depend on -- an explicit, minimal, always-
+    the-same selection keeps this a fast correctness check, not a style audit.
+
+    `--per-file-ignores __init__.py:F401`: a package __init__.py that re-exports
+    names (`from .mod import Thing`) trips F401 "imported but unused" -- but that
+    IS the file's purpose, and it's a brand-new file with no baseline to forgive
+    it against, so without this exception a maker creating a re-exporting package
+    (exactly what the RAG POC does with rag_agent/__init__.py) would fail
+    self_check on the single most conventional line in Python packaging. Scoped
+    to F401 in __init__.py only; genuine syntax errors and other pyflakes issues
+    there are still caught.
+    """
+    if not files:
+        return [], None
+    result = run_command(
+        "ruff",
+        ["check", *files, "--select", "E9,F", "--per-file-ignores", "__init__.py:F401",
+         "--output-format", "json", *[f"--extend-exclude={d}" for d in harness_excludes]],
+        cwd=cwd,
+        timeout_s=timeout,
+    )
+    if result.timed_out:
+        return None, result
+    try:
+        findings = json.loads(result.stdout) if result.stdout.strip() else []
+    except json.JSONDecodeError:
+        return None, result
+    return findings, result
+
+
+def _ruff_new_findings(worktree_dir: Path, changed: list[str], handle: WorktreeHandle,
+                       harness_excludes: list[str], timeout: int):
+    """E9,F ruff findings the maker *introduced this run* -- current findings
+    on the changed files, minus those already present in each file at the run's
+    baseline (HEAD), compared per (relative-path, rule-code) so line shifts from
+    the edit don't matter. Files the maker newly created have no baseline, so
+    every finding in them counts (a brand-new file should be clean).
+
+    Why this exists: scoping ruff to changed files (previous fix) still gated on
+    pre-existing debt whenever the maker legitimately had to touch a file that
+    already carried it -- the live run escalated 4x because app.py's import line
+    genuinely needed updating for the module move, and app.py already had an
+    unrelated duplicate `import os` (F811). The maker reported "all 6 BDD
+    scenarios pass" every attempt, but self_check blocked before bdd_gate could
+    confirm it. Forgiving pre-existing findings fixes that while still catching
+    anything the maker actually breaks.
+
+    Returns (new_findings, current_result). new_findings is None if ruff output
+    couldn't be parsed at all (caller falls back to opaque rc)."""
+    current, current_result = _run_ruff_json(changed, worktree_dir, harness_excludes, timeout)
+    if current is None:
+        return None, current_result
+    if not current:
+        return [], current_result
+
+    # A moved file has no blob at its new path in HEAD; without this its
+    # (pre-existing) content would all read as newly introduced. renamed_paths
+    # lets us look the baseline up at the file's OLD path instead. Written into
+    # tmp under the NEW path so the (relative-path, code) comparison key lines
+    # up with the current findings.
+    renames = worktree_renamed_paths(handle)
+    with tempfile.TemporaryDirectory() as tmp:
+        tmp_path = Path(tmp)
+        baseline_files: list[str] = []
+        for rel in changed:
+            content = worktree_file_at_baseline(handle, rel)
+            if content is None and rel in renames:
+                content = worktree_file_at_baseline(handle, renames[rel])
+            if content is None:
+                continue  # genuinely new file this run -> no baseline; its findings all count
+            dest = tmp_path / rel
+            dest.parent.mkdir(parents=True, exist_ok=True)
+            dest.write_text(content, encoding="utf-8")
+            baseline_files.append(rel)
+        baseline, _ = _run_ruff_json(baseline_files, tmp_path, [], timeout)
+        baseline = baseline or []
+
+    def _key(finding: dict, root: Path) -> tuple[str, str]:
+        fname = finding.get("filename", "")
+        try:
+            rel = os.path.relpath(fname, root)
+        except ValueError:
+            rel = fname
+        return (rel.replace(os.sep, "/"), finding.get("code") or "")
+
+    baseline_counts = Counter(_key(f, tmp_path) for f in baseline)
+    seen: Counter = Counter()
+    new: list[dict] = []
+    for f in current:
+        k = _key(f, worktree_dir)
+        seen[k] += 1
+        if seen[k] > baseline_counts.get(k, 0):
+            new.append(f)
+    return new, current_result
+
+
+def _render_ruff_findings(findings: list[dict]) -> str:
+    """One line per finding for the run report (json output isn't human-facing)."""
+    if not findings:
+        return ""
+    lines = []
+    for f in findings:
+        loc = f.get("location") or {}
+        rel = f.get("filename", "?")
+        lines.append(f"{rel}:{loc.get('row', '?')}:{loc.get('column', '?')} {f.get('code')} {f.get('message', '')}")
+    return "\n".join(lines)
+
+
+def _is_under_any(rel_path: str, dirs: set[str]) -> bool:
+    """True if rel_path lives inside one of `dirs` (or is one of them)."""
+    parts = Path(rel_path).parts
+    for d in dirs:
+        dparts = Path(d).parts
+        if len(parts) >= len(dparts) and tuple(parts[: len(dparts)]) == dparts:
+            return True
+    return False
\ No newline at end of file
diff --git a/coding_agent/llm_boundaries.py b/coding_agent/llm_boundaries.py
new file mode 100644
index 0000000..092cd63
--- /dev/null
+++ b/coding_agent/llm_boundaries.py
@@ -0,0 +1,134 @@
+"""Isolated LLM invocation wrappers for the Coding Engineer loop.
+
+Extracted from ``coding_agent/engine.py`` during the single-responsibility
+refactor.  Every LLM call in the loop goes through one of these boundary
+functions so tests can monkeypatch just the model call and exercise the real
+graph, worktree, gates, and report writer around it.
+"""
+
+from __future__ import annotations
+
+from typing import Any
+
+from langchain.agents import AgentExecutor, create_tool_calling_agent
+from langchain_core.messages import HumanMessage
+from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
+
+from coding_agent.gates import _read_step_defs
+from coding_agent.maker_tools import _build_maker_tools, _maker_task_text
+from coding_agent.prompts import (
+    AUTHOR_BDD_PROMPT,
+    DIAGNOSE_PROMPT,
+    INTAKE_PROMPT,
+    MAKER_SYSTEM_PROMPT,
+    PLAN_JUDGE_PROMPT,
+    PLAN_PROPOSE_PROMPT,
+    REVIEW_PROMPT,
+)
+from coding_agent.schemas import (
+    BddAuthorResult,
+    DiagnosisResult,
+    PlanJudgement,
+    PlanProposal,
+    ReviewVerdict,
+    TargetSpec,
+)
+from coding_agent.state import CodingLoopState
+from coding_agent.structured import invoke_structured
+from coding_agent.tools.code_exec import Jail
+
+
+def _llm_parse_target_spec(llm, goal: str, target_dir: str) -> TargetSpec:
+    prompt = INTAKE_PROMPT.format(goal=goal, target_dir=target_dir)
+    return invoke_structured(llm, TargetSpec, prompt)
+
+
+def _llm_author_bdd(llm, state: CodingLoopState) -> BddAuthorResult:
+    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
+    prompt = AUTHOR_BDD_PROMPT.format(
+        goal=state["goal"],
+        acceptance_criteria="\n".join(f"- {c}" for c in criteria) or "(none extracted)",
+    )
+    return invoke_structured(llm, BddAuthorResult, prompt)
+
+
+def _llm_diagnose(llm, state: CodingLoopState, phase: str, failure_detail: str) -> DiagnosisResult:
+    lessons = state.get("lessons") or []
+    lesson_lines = (
+        "\n".join(f"- attempt {ls.get('attempt')}: {ls.get('insight')}" for ls in lessons[-5:])
+        or "(none yet)"
+    )
+    prompt = DIAGNOSE_PROMPT.format(
+        goal=state["goal"], phase=phase, failure_detail=failure_detail, lessons=lesson_lines
+    )
+    return invoke_structured(llm, DiagnosisResult, prompt)
+
+
+def _lessons_block(state: CodingLoopState) -> str:
+    """Aggregated lessons for the ToT re-planning prompt (the GoT step) -- empty
+    on the first planning pass, populated once plans start dying."""
+    lessons = state.get("lessons") or []
+    if not lessons:
+        return ""
+    body = "\n".join(f"- ({ls.get('category')}) {ls.get('insight')}" for ls in lessons[-8:])
+    return f"\nLessons from earlier failed attempts (avoid repeating these):\n{body}\n"
+
+
+def _criteria_text(state: CodingLoopState) -> str:
+    criteria = (state.get("spec") or {}).get("acceptance_criteria", [])
+    return "\n".join(f"- {c}" for c in criteria) or "(none extracted)"
+
+
+def _llm_propose_plans(llm, state: CodingLoopState, k: int) -> PlanProposal:
+    prompt = PLAN_PROPOSE_PROMPT.format(
+        k=k, goal=state["goal"], acceptance_criteria=_criteria_text(state), lessons_block=_lessons_block(state)
+    )
+    return invoke_structured(llm, PlanProposal, prompt)
+
+
+def _llm_judge_plans(llm, state: CodingLoopState, plans: list[dict]) -> PlanJudgement:
+    plans_block = "\n".join(
+        f"[{i}] {p.get('rationale', '')}\n" + "\n".join(f"    - {s}" for s in p.get("steps", []))
+        for i, p in enumerate(plans)
+    )
+    prompt = PLAN_JUDGE_PROMPT.format(
+        goal=state["goal"],
+        acceptance_criteria=_criteria_text(state),
+        lessons_block=_lessons_block(state),
+        plans_block=plans_block,
+    )
+    return invoke_structured(llm, PlanJudgement, prompt)
+
+
+def _llm_review(llm, state: CodingLoopState) -> ReviewVerdict:
+    bdd = state.get("bdd_report") or {}
+    step_defs = _read_step_defs(state)
+    prompt = REVIEW_PROMPT.format(
+        goal=state["goal"],
+        acceptance_criteria=_criteria_text(state),
+        diff=(state.get("last_diff") or "(no diff)")[:6000],
+        step_defs=step_defs[:6000],
+        test_output=(bdd.get("stdout") or "(no output)")[:2000],
+    )
+    return invoke_structured(llm, ReviewVerdict, prompt)
+
+
+def _run_maker(llm, jail: Jail, state: CodingLoopState) -> dict[str, Any]:
+    tools = _build_maker_tools(jail, state["budgets"])
+    prompt = ChatPromptTemplate.from_messages(
+        [
+            ("system", MAKER_SYSTEM_PROMPT),
+            MessagesPlaceholder(variable_name="messages"),
+            MessagesPlaceholder(variable_name="agent_scratchpad"),
+        ]
+    )
+    agent = create_tool_calling_agent(llm, tools, prompt)
+    # max_iterations=8 was too tight for a real multi-file change: the first
+    # live self-hosted run ("Agent stopped due to max iterations" on all 4
+    # attempts) needed read+write on rag_research_chatbot.py, a new
+    # rag_agent/__init__.py, delete of the old file, an app.py import edit,
+    # and a run_pytest check -- more tool calls than a genuine refactor-shaped
+    # goal can fit in 8. Raised to a more realistic budget for multi-file work.
+    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=20)
+    task_message = HumanMessage(content=_maker_task_text(state))
+    return executor.invoke({"messages": [task_message]})
\ No newline at end of file
diff --git a/coding_agent/maker_tools.py b/coding_agent/maker_tools.py
new file mode 100644
index 0000000..14a3884
--- /dev/null
+++ b/coding_agent/maker_tools.py
@@ -0,0 +1,109 @@
+"""Maker tool construction for the Coding Engineer loop.
+
+Extracted from ``coding_agent/engine.py`` during the single-responsibility
+refactor.  Builds the filesystem/pytest tool surface the maker agent uses
+and renders the task text fed to it.
+"""
+
+from __future__ import annotations
+
+from langchain_core.messages import HumanMessage
+from langchain_core.prompts import MessagesPlaceholder
+from langchain_core.tools import tool
+from langchain.agents import AgentExecutor, create_tool_calling_agent
+
+from coding_agent.prompts import MAKER_SYSTEM_PROMPT
+from coding_agent.state import Budgets, CodingLoopState
+from coding_agent.tools.code_exec import Jail, run_command
+
+
+def _build_maker_tools(jail: Jail, budgets: Budgets) -> list:
+    """Read/list/write/delete/move plus a scoped pytest runner. `run_command`
+    supports more binaries than are exposed here (e.g. `git`, `ruff`) --
+    self_check/bdd_gate already cover those; the maker doesn't need them
+    directly. delete_file/move_file were added after Phase 1 shipped (see
+    PHASED_PLAN.md "Phase 1 follow-up") once a real refactor-shaped goal
+    (moving a module to a subfolder) showed write-only wasn't enough for a
+    clean move -- the old path would just be left behind as a duplicate."""
+
+    @tool
+    def read_file(path: str) -> str:
+        """Read a text file's contents. `path` is relative to the worktree root."""
+        try:
+            return jail.read_file(path)
+        except (JailViolation, OSError) as exc:
+            return f"ERROR: {exc}"
+
+    @tool
+    def list_dir(path: str = ".") -> str:
+        """List a directory's entries. `path` is relative to the worktree root."""
+        try:
+            return "\n".join(jail.list_dir(path))
+        except (JailViolation, OSError) as exc:
+            return f"ERROR: {exc}"
+
+    @tool
+    def write_file(path: str, content: str) -> str:
+        """Write (create or overwrite) a text file with the given full content.
+        `path` is relative to the worktree root. Refuses frozen BDD feature files."""
+        try:
+            jail.write_file(path, content)
+            return f"wrote {path}"
+        except (JailViolation, OSError) as exc:
+            return f"ERROR: {exc}"
+
+    @tool
+    def delete_file(path: str) -> str:
+        """Delete a file. `path` is relative to the worktree root. Refuses
+        frozen BDD feature files. Use this to remove a file after moving its
+        content elsewhere with write_file -- write_file alone never deletes
+        the original."""
+        try:
+            jail.delete_file(path)
+            return f"deleted {path}"
+        except (JailViolation, OSError) as exc:
+            return f"ERROR: {exc}"
+
+    @tool
+    def move_file(src_path: str, dst_path: str) -> str:
+        """Move/rename a file. Both paths are relative to the worktree root.
+        Refuses the operation if either end is a frozen BDD feature file."""
+        try:
+            jail.move_file(src_path, dst_path)
+            return f"moved {src_path} -> {dst_path}"
+        except (JailViolation, OSError) as exc:
+            return f"ERROR: {exc}"
+
+    @tool
+    def run_pytest(pytest_args: str = "") -> str:
+        """Run pytest inside the worktree to check your work before finishing.
+        `pytest_args` is an optional space-separated string of extra pytest arguments."""
+        # Deliberately not named `args` -- pydantic's function-wrapping internals
+        # (used by @tool's schema inference) reserve that name as a synthetic
+        # field for wrapping Python's own *args, so a real parameter literally
+        # named `args` silently gets renamed to `v__args` in the generated
+        # schema, which the tool-calling model then can't satisfy. Confirmed
+        # live: this was the exact "run_pytest() got an unexpected keyword
+        # argument 'v__args'" failure from the first two live runs.
+        extra = pytest_args.split() if pytest_args else []
+        result = run_command("pytest", ["-q", *extra], cwd=jail.root, timeout_s=budgets["cmd_timeout_s"])
+        return f"returncode={result.returncode}\n{result.stdout}\n{result.stderr}"
+
+    return [read_file, list_dir, write_file, delete_file, move_file, run_pytest]
+
+
+def _maker_task_text(state: CodingLoopState) -> str:
+    spec = state.get("spec") or {}
+    lessons = state.get("lessons") or []
+    lesson_lines = "\n".join(f"- {lesson['insight']}" for lesson in lessons[-3:]) or "(none yet)"
+    criteria = "\n".join(f"- {c}" for c in spec.get("acceptance_criteria", [])) or "(none extracted)"
+    return (
+        f"Goal: {state['goal']}\n\n"
+        f"Acceptance criteria:\n{criteria}\n\n"
+        f"Frozen BDD scenarios (do not edit): {', '.join(state.get('feature_paths', [])) or '(none)'}\n\n"
+        f"Recent lessons from earlier attempts:\n{lesson_lines}\n\n"
+        "Make the smallest change that could make the tests pass. You may read files, "
+        "list directories, write files, delete files, move/rename files, and run pytest "
+        "to check your work. If you move something, delete the original -- write_file "
+        "alone does not remove it."
+    )
\ No newline at end of file
diff --git a/coding_agent/nodes.py b/coding_agent/nodes.py
new file mode 100644
index 0000000..42ddbd0
--- /dev/null
+++ b/coding_agent/nodes.py
@@ -0,0 +1,731 @@
+"""StateGraph node implementations and conditional routing for the Coding Engineer loop.
+
+Extracted from ``coding_agent/engine.py`` during the single-responsibility
+refactor.  Each node is a thin orchestrator: it calls a boundary function
+(``coding_agent.llm_boundaries``), runs a gate (``coding_agent.gates``), or
+does pure-code state bookkeeping, then returns a state update dict.
+
+Monkeypatch compatibility: tests patch boundary functions and ``get_llm`` on
+the ``coding_agent.engine`` module (e.g. ``coding_agent.engine._run_maker``).
+So that those patches take effect, nodes look up those callables through the
+engine module at *call time* via the lazy ``_eng()`` accessor below, rather
+than holding local references that would bypass the patch.
+"""
+
+from __future__ import annotations
+
+import os
+import time
+from pathlib import Path
+
+from langgraph.types import interrupt
+
+from coding_agent.gates import (
+    _harness_exclude_dirs,
+    _is_under_any,
+    _read_failures,
+    _read_json_report,
+    _render_ruff_findings,
+    _ruff_new_findings,
+)
+from coding_agent.report import stop_flag_set, write_run_report
+from coding_agent.schemas import ReviewVerdict
+from coding_agent.signatures import (
+    compute_signature,
+    review_signature,
+    signature_for_failure,
+    template_message,
+)
+from coding_agent.state import (
+    DEFAULT_BUDGETS,
+    CodingLoopState,
+    Plan,
+    _handle_from_state,
+    _loop_state_dir,
+    _status_message,
+)
+from coding_agent.structured import StructuredOutputError
+from coding_agent.tools.code_exec import Jail, run_command
+from coding_agent.tools.worktree import (
+    create_worktree,
+    changed_files as worktree_changed_files,
+    commit as worktree_commit,
+    diff as worktree_diff,
+)
+
+try:
+    # telemetry lives at the repo root; it's optional and degrades to no-ops.
+    # Used here only for its pure token-usage extractor (no OTel import), so a
+    # token tally can ride in graph state and feed the Â§3.4 token budget.
+    from telemetry import extract_token_usage as _extract_token_usage
+except Exception:  # noqa: BLE001 -- telemetry is optional; never let its absence break the engine
+    def _extract_token_usage(_graph_output) -> tuple[int, int]:
+        return 0, 0
+
+
+# ---------------------------------------------------------------------------
+# lazy engine accessor -- see module docstring for why this exists
+# ---------------------------------------------------------------------------
+
+_engine = None
+
+
+def _eng():
+    """Return the ``coding_agent.engine`` module, importing it lazily.
+
+    ``engine`` imports ``nodes`` at module load time, so ``nodes`` cannot
+    import ``engine`` at its own module level (circular).  By the time any
+    node *runs*, ``engine`` is fully loaded, so this lazy lookup is safe and
+    lets tests monkeypatch attributes on ``coding_agent.engine`` (e.g.
+    ``_run_maker``, ``get_llm``) and have the patches take effect here.
+    """
+    global _engine
+    if _engine is None:
+        import coding_agent.engine as e
+        _engine = e
+    return _engine
+
+
+# ---------------------------------------------------------------------------
+# small node-local helpers
+# ---------------------------------------------------------------------------
+
+
+def _summarize_failure(state: CodingLoopState) -> str:
+    """Pure-code, no-LLM failure summary for the Phase 1 lesson log.
+
+    Phase 2 (CODING_ENGINEER.md Â§3.4) replaces this with an LLM-classified,
+    normalised failure_signature; this stub keeps the state shape (lessons
+    with an `insight` string) stable across that upgrade.
+    """
+    test_report = state.get("test_report") or {}
+    bdd_report = state.get("bdd_report") or {}
+    if not test_report.get("passed", True):
+        return (
+            f"self_check failed â€” ruff rc={test_report.get('ruff', {}).get('returncode')}, "
+            f"pytest rc={test_report.get('pytest', {}).get('returncode')}, "
+            f"summary={test_report.get('pytest', {}).get('summary')}"
+        )
+    if not bdd_report.get("passed", True):
+        return f"bdd_gate failed â€” pytest rc={bdd_report.get('returncode')}, summary={bdd_report.get('summary')}"
+    return "unknown failure (neither self_check nor bdd_report marked failed)"
+
+
+def _fallback_plan() -> Plan:
+    return {
+        "id": "plan-1",
+        "steps": ["Implement the goal against the acceptance criteria; iterate using self_check/bdd_gate feedback."],
+        "rationale": "fallback single plan (propose/judge unavailable)",
+        "score": 1.0,
+        "status": "untried",
+    }
+
+
+def _score_plans(state: CodingLoopState, plans: list[Plan], exclude: set[str]) -> list[Plan]:
+    """Judge (secondary role, temperature 0) scores the not-yet-exhausted plans.
+    On re-entry the aggregated lessons ride along in the prompt -- the GoT step,
+    so a plan that would repeat a known dead end scores low. Degrades gracefully:
+    if the judge call fails, keep any existing scores and otherwise fall back to
+    proposal order (first proposed = best)."""
+    to_score = [p for p in plans if p["id"] not in exclude]
+    if not to_score:
+        return plans
+    secondary = _eng().get_llm("secondary", temperature=0.0)
+    try:
+        judgement = _eng()._llm_judge_plans(secondary, state, to_score)
+        by_index = {s.plan_index: s.score for s in judgement.scores}
+        for i, p in enumerate(to_score):
+            if i in by_index:
+                p["score"] = float(by_index[i])
+    except StructuredOutputError:
+        for i, p in enumerate(to_score):
+            if not p.get("score"):
+                p["score"] = float(len(to_score) - i)
+    return plans
+
+
+# ---------------------------------------------------------------------------
+# nodes
+# ---------------------------------------------------------------------------
+
+
+def intake_node(state: CodingLoopState) -> dict:
+    budgets = {**DEFAULT_BUDGETS, **(state.get("budgets") or {})}
+    llm = _eng().get_llm("primary")
+    try:
+        spec = _eng()._llm_parse_target_spec(llm, state["goal"], state["target_dir"])
+    except StructuredOutputError as exc:
+        # Escalate gracefully (with a report) instead of letting the raw
+        # exception blow up the graph -- the first live run surfaced exactly
+        # this as an unhandled stack trace in the UI. See structured.py.
+        return {
+            "budgets": budgets,
+            "run_started_at": time.time(),
+            "status": "escalated",
+            "escalation_reason": f"intake structured-output failure: {exc}",
+            "messages": [_status_message("intake", False, note=str(exc)[:200])],
+        }
+
+    if not spec.is_suitable:
+        return {
+            "spec": spec.model_dump(),
+            "budgets": budgets,
+            "run_started_at": time.time(),
+            "status": "escalated",
+            "escalation_reason": f"unsuitable goal: {spec.rejection_reason or 'not checkable'}",
+            "messages": [_status_message("intake", False, note=spec.rejection_reason or "goal rejected")],
+        }
+
+    handle = create_worktree(Path(state["target_dir"]), state["run_id"], _loop_state_dir())
+
+    return {
+        "spec": spec.model_dump(),
+        "budgets": budgets,
+        "worktree_dir": str(handle.worktree_dir),
+        "branch": handle.branch,
+        "target_dir": str(handle.target_dir),
+        "is_fallback_copy": handle.is_fallback_copy,
+        "run_started_at": time.time(),
+        "attempt": 0,
+        "total_attempts": 0,
+        "lessons": [],
+        "candidate_plans": [],
+        "feature_paths": [],
+        "status": "planning",
+        "messages": [_status_message("intake", True, note=f"worktree ready at {handle.worktree_dir}")],
+    }
+
+
+def _route_after_intake(state: CodingLoopState) -> str:
+    return "escalate" if state.get("status") == "escalated" else "author_bdd"
+
+
+def _route_after_author_bdd(state: CodingLoopState) -> str:
+    return "escalate" if state.get("status") == "escalated" else "plan_tot"
+
+
+def author_bdd_node(state: CodingLoopState) -> dict:
+    worktree_dir = Path(state["worktree_dir"])
+    # Bug found on the first real self-hosted run: an unscoped rglob picked up
+    # coding_agent/sample_target/features/calculator.feature -- the agent's own
+    # demo fixture -- and froze it as the "definition of done" for an unrelated
+    # goal (moving rag_research_chatbot.py). Same harness-exclusion rule as
+    # self_check/bdd_gate (_harness_exclude_dirs), applied here too now.
+    harness_excludes = set(_harness_exclude_dirs(worktree_dir))
+    existing = sorted(
+        str(p.relative_to(worktree_dir)).replace(os.sep, "/")
+        for p in worktree_dir.rglob("*.feature")
+        if ".git" not in p.parts and not harness_excludes & set(p.relative_to(worktree_dir).parts)
+    )
+
+    if existing:
+        return {
+            "feature_paths": existing,
+            "status": "planning",
+            "messages": [
+                _status_message("author_bdd", True, note=f"adopted existing: {', '.join(existing)}")
+            ],
+        }
+
+    llm = _eng().get_llm("primary", temperature=0.3)
+    try:
+        result = _eng()._llm_author_bdd(llm, state)
+    except StructuredOutputError as exc:
+        return {
+            "status": "escalated",
+            "escalation_reason": f"author_bdd structured-output failure: {exc}",
+            "messages": [_status_message("author_bdd", False, note=str(exc)[:200])],
+        }
+
+    if state.get("hitl_bdd_approval") and result.ambiguity:
+        payload = interrupt(
+            {
+                "node": "author_bdd",
+                "reason": result.ambiguity_reason,
+                "draft_feature_gherkin": result.feature_gherkin,
+                "draft_feature_relative_path": result.feature_relative_path,
+            }
+        )
+        if isinstance(payload, dict):
+            result.feature_gherkin = payload.get("feature_gherkin", result.feature_gherkin)
+            result.feature_relative_path = payload.get("feature_relative_path", result.feature_relative_path)
+
+    jail = Jail(root=worktree_dir)  # nothing frozen yet -- these are the files being authored
+    jail.write_file(result.feature_relative_path, result.feature_gherkin)
+    jail.write_file(result.step_defs_relative_path, result.step_defs_python)
+
+    return {
+        "feature_paths": [result.feature_relative_path],
+        "status": "planning",
+        "messages": [_status_message("author_bdd", True, note=f"drafted {result.feature_relative_path}")],
+    }
+
+
+def plan_tot_node(state: CodingLoopState) -> dict:
+    """Tree-of-Thought planning (CODING_ENGINEER.md Â§3.6). First entry: the
+    primary model proposes k distinct plans (hot), the secondary-role judge
+    scores them (cold), and the best untried plan becomes active. Re-entry
+    (after diagnose retires a stalled plan): the surviving candidates are
+    RE-SCORED with the aggregated lessons in the prompt -- not regenerated --
+    and the next best untried plan is selected."""
+    budgets = state["budgets"]
+    k = budgets.get("max_plans", 3)
+    exhausted = set(state.get("exhausted_plan_ids") or [])
+    existing = list(state.get("candidate_plans") or [])
+
+    if not existing:
+        primary = _eng().get_llm("primary", temperature=0.8)
+        try:
+            proposal = _eng()._llm_propose_plans(primary, state, k)
+            existing = [
+                {"id": f"plan-{i + 1}", "steps": list(p.steps), "rationale": p.rationale, "score": 0.0,
+                 "status": "untried"}
+                for i, p in enumerate(proposal.plans)
+            ] or [_fallback_plan()]
+        except StructuredOutputError:
+            existing = [_fallback_plan()]
+
+    existing = _score_plans(state, existing, exclude=exhausted)
+
+    candidates = [p for p in existing if p["id"] not in exhausted]
+    if not candidates:  # defensive -- diagnose escalates before this can happen
+        return {
+            "candidate_plans": existing,
+            "status": "escalated",
+            "escalation_reason": "no_plans_left",
+            "diagnosis": {"action": "escalate"},
+        }
+
+    best = max(candidates, key=lambda p: p.get("score", 0.0))
+    for p in existing:
+        p["status"] = "active" if p["id"] == best["id"] else ("exhausted" if p["id"] in exhausted else "untried")
+
+    return {
+        "candidate_plans": existing,
+        "active_plan_id": best["id"],
+        "status": "coding",
+        "attempt": 0,  # each plan gets its own per-plan attempt budget
+        "messages": [
+            _status_message("plan_tot", True, note=f"selected {best['id']} (score {best.get('score', 0):.1f}) of {len(existing)}")
+        ],
+    }
+
+
+def code_node(state: CodingLoopState) -> dict:
+    jail = Jail(root=Path(state["worktree_dir"]), frozen=frozenset(Path(p) for p in state.get("feature_paths", [])))
+    llm = _eng().get_llm("primary", temperature=0.2)
+    maker_result = _eng()._run_maker(llm, jail, state)
+
+    handle = _handle_from_state(state)
+    diff_text = worktree_diff(handle)
+
+    summary = maker_result.get("output", "") if isinstance(maker_result, dict) else str(maker_result)
+    # Best-effort token tally: the maker (AgentExecutor) is where the bulk of
+    # tokens go, and its result may carry usage on the final AIMessage. Ollama
+    # often omits usage on tool-calling turns, so this under-counts rather than
+    # over-counts -- the token budget stays a safety valve, not a precise meter.
+    p_tok, c_tok = _extract_token_usage(maker_result if isinstance(maker_result, dict) else {})
+    return {
+        "last_diff": diff_text,
+        "tokens_used": state.get("tokens_used", 0) + p_tok + c_tok,
+        "status": "coding",
+        # A new attempt invalidates any prior review verdict -- clear it so
+        # diagnose (Phase 3) doesn't mistake a stale reject for this attempt's
+        # outcome when a later gate fails first.
+        "review_result": None,
+        "messages": [_status_message("code", True, note=str(summary)[:200])],
+    }
+
+
+def self_check_node(state: CodingLoopState) -> dict:
+    worktree_dir = Path(state["worktree_dir"])
+    timeout = state["budgets"]["cmd_timeout_s"]
+    harness_excludes = _harness_exclude_dirs(worktree_dir)
+
+    # Scope ruff to files changed this run AND only fail on findings this run
+    # introduced (see _ruff_new_findings for the full why). Two live-run bugs
+    # drove this: (1) an unscoped `ruff check .` failed on pre-existing debt in
+    # files the maker never touched; (2) scoping to changed files still failed
+    # on pre-existing debt in a file the maker legitimately *had* to touch
+    # (app.py's import line). Differential-vs-baseline forgives both.
+    #
+    # Also exclude the frozen BDD harness (the feature dir + its step defs) and
+    # the agent's own package: those aren't the maker's implementation change.
+    # author_bdd *generates* the step-defs file, and it routinely leaves an
+    # unused `import pytest` in it (F401) -- that's bdd_gate's code to run, not
+    # self_check's to lint. The live RAG POC's move actually completed, and the
+    # ONLY thing blocking finalization was self_check flagging F401 in that
+    # generated step-defs file.
+    excluded_dirs = set(harness_excludes) | {
+        str(Path(fp).parent).replace(os.sep, "/") for fp in state.get("feature_paths", [])
+    }
+    handle = _handle_from_state(state)
+    changed = [
+        p
+        for p in worktree_changed_files(handle)
+        if (worktree_dir / p).exists() and p.endswith(".py") and not _is_under_any(p, excluded_dirs)
+    ]
+
+    new_findings, ruff_result = _ruff_new_findings(worktree_dir, changed, handle, harness_excludes, timeout)
+    if new_findings is None:
+        # Couldn't parse ruff's json (or it timed out) -> fall back to an opaque
+        # rc check on the changed files, so a broken ruff invocation fails safe
+        # rather than silently passing.
+        fallback = run_command(
+            "ruff",
+            ["check", *(changed or ["."]), "--select", "E9,F", "--per-file-ignores", "__init__.py:F401",
+             *[f"--extend-exclude={d}" for d in harness_excludes]],
+            cwd=worktree_dir,
+            timeout_s=timeout,
+        )
+        ruff_returncode = fallback.returncode
+        ruff_stdout = fallback.stdout
+        ruff_stderr = fallback.stderr
+        ruff_timed_out = fallback.timed_out
+        ruff_passed = fallback.returncode == 0 and not fallback.timed_out
+    else:
+        ruff_returncode = 1 if new_findings else 0
+        ruff_stdout = _render_ruff_findings(new_findings)
+        ruff_stderr = ruff_result.stderr if ruff_result else ""
+        ruff_timed_out = ruff_result.timed_out if ruff_result else False
+        ruff_passed = not new_findings
+
+    ignore_args: list[str] = []
+    for feature_path in state.get("feature_paths", []):
+        ignore_args.extend(["--ignore", str(Path(feature_path).parent)])
+    for excluded in harness_excludes:
+        ignore_args.extend(["--ignore", excluded])
+
+    report_file = worktree_dir / ".self_check_report.json"
+    pytest_result = run_command(
+        "pytest",
+        ["-q", *ignore_args, "--json-report", f"--json-report-file={report_file.name}"],
+        cwd=worktree_dir,
+        timeout_s=timeout,
+    )
+    summary = _read_json_report(report_file)
+    failures = _read_failures(report_file)
+    report_file.unlink(missing_ok=True)
+
+    # pytest exits 5 when it collects zero tests -- expected when the only
+    # tests in scope ARE the frozen BDD scenarios (self_check ignores them;
+    # bdd_gate is the node responsible for actually finding and running them).
+    pytest_ok = pytest_result.returncode in (0, 5) and not pytest_result.timed_out
+    passed = ruff_passed and pytest_ok
+
+    test_report = {
+        "ruff": {
+            "returncode": ruff_returncode,
+            "stdout": ruff_stdout,
+            "stderr": ruff_stderr,
+            "timed_out": ruff_timed_out,
+        },
+        "pytest": {
+            "returncode": pytest_result.returncode,
+            "stdout": pytest_result.stdout,
+            "stderr": pytest_result.stderr,
+            "timed_out": pytest_result.timed_out,
+            "summary": summary,
+            "failures": failures,  # normalised for signing -- see signatures.py / diagnose
+        },
+        # ruff findings are signable too (a ruff-only self_check failure has no
+        # pytest failure): the sorted rule codes are a stable descriptor.
+        "ruff_codes": sorted({f.get("code") for f in (new_findings or []) if f.get("code")}),
+        "passed": passed,
+    }
+    return {"test_report": test_report, "status": "testing", "messages": [_status_message("self_check", passed)]}
+
+
+def _route_after_self_check(state: CodingLoopState) -> str:
+    return "bdd_gate" if state["test_report"]["passed"] else "diagnose"
+
+
+def bdd_gate_node(state: CodingLoopState) -> dict:
+    worktree_dir = Path(state["worktree_dir"])
+    timeout = state["budgets"]["cmd_timeout_s"]
+    feature_paths = state.get("feature_paths", [])
+    scope_dirs = sorted({str(Path(p).parent) for p in feature_paths}) or ["."]
+    # Defensive, not just belt-and-braces for the common case: scope_dirs
+    # only falls back to "." if feature_paths is somehow empty here, but
+    # when it does, this is what stops that fallback from recursing into
+    # the agent's own harness -- see _harness_exclude_dirs.
+    ignore_args = [arg for excluded in _harness_exclude_dirs(worktree_dir) for arg in ("--ignore", excluded)]
+
+    report_file = worktree_dir / ".bdd_report.json"
+    result = run_command(
+        "pytest",
+        ["-q", *scope_dirs, *ignore_args, "--json-report", f"--json-report-file={report_file.name}"],
+        cwd=worktree_dir,
+        timeout_s=timeout,
+    )
+    summary = _read_json_report(report_file)
+    failures = _read_failures(report_file)
+    report_file.unlink(missing_ok=True)
+
+    passed = result.returncode == 0 and not result.timed_out
+    bdd_report = {
+        "returncode": result.returncode,
+        "stdout": result.stdout,
+        "stderr": result.stderr,
+        "timed_out": result.timed_out,
+        "summary": summary,
+        "failures": failures,  # normalised for signing -- see signatures.py / diagnose
+        "passed": passed,
+    }
+    return {"bdd_report": bdd_report, "status": "testing", "messages": [_status_message("bdd_gate", passed)]}
+
+
+def _route_after_bdd_gate(state: CodingLoopState) -> str:
+    # Phase 3: a green bdd_gate no longer finalizes directly -- the adversarial
+    # reviewer (checker) gets the last word (CODING_ENGINEER.md Â§3.1/Â§3.3).
+    return "review" if state["bdd_report"]["passed"] else "diagnose"
+
+
+def review_node(state: CodingLoopState) -> dict:
+    """Adversarial checker (CODING_ENGINEER.md Â§3.3), always the secondary role
+    (Â§3.5) -- a different model catches more than a different prompt on the same
+    one. Sees the spec, diff, step defs, and (green) test output, NOT the maker's
+    reasoning, and specifically hunts trivial-pass hacks in the step defs.
+    reject requires a blocker/major finding; minor-only downgrades to
+    approve_with_notes (notes land in the report, run still finalizes)."""
+    if stop_flag_set(state["run_id"], _loop_state_dir()):
+        return {"status": "escalated", "escalation_reason": "stopped by user", "diagnosis": {"action": "escalate"}}
+
+    secondary = _eng().get_llm("secondary", temperature=0.0)
+    try:
+        verdict = _eng()._llm_review(secondary, state)
+    except StructuredOutputError:
+        # A review hiccup must not block an already-green run -> approve with a note.
+        verdict = ReviewVerdict(verdict="approve_with_notes", findings=[])
+
+    blocking = [f for f in verdict.findings if f.severity in ("blocker", "major")]
+    is_reject = verdict.verdict == "reject" and bool(blocking)
+    review = {
+        "verdict": "reject" if is_reject else ("approve_with_notes" if verdict.findings else "approve"),
+        "findings": [f.model_dump() for f in verdict.findings],
+        "blocking": [f.model_dump() for f in blocking],
+    }
+    note = f"{review['verdict']}" + (f" ({len(blocking)} blocking)" if blocking else "")
+    return {"review_result": review, "status": "testing", "messages": [_status_message("review", not is_reject, note=note)]}
+
+
+def _route_after_review(state: CodingLoopState) -> str:
+    review = state.get("review_result") or {}
+    return "diagnose" if review.get("verdict") == "reject" and review.get("blocking") else "finalize"
+
+
+_MAX_FLAKE_FREE_RETRIES = 2  # a genuinely flaky gate shouldn't spin forever on "free" retries
+
+
+def _failed_phase(state: CodingLoopState) -> str | None:
+    """Which gate failed this attempt (closed set, matches Â§3.4's `phase`).
+    A review reject is only 'this attempt's' failure because code_node clears
+    the prior review at the start of every attempt, so a stale reject can't
+    shadow a later self_check/bdd_gate failure."""
+    review = state.get("review_result") or {}
+    if review.get("verdict") == "reject" and review.get("blocking"):
+        return "review"
+    if not (state.get("test_report") or {}).get("passed", True):
+        return "self_check"
+    if not (state.get("bdd_report") or {}).get("passed", True):
+        return "bdd_gate"
+    return None
+
+
+def _signature_and_detail(state: CodingLoopState, phase: str) -> tuple[str, str]:
+    """(failure_signature, human detail) for the failed gate. Prefers the first
+    failing pytest test (the Â§3.4 recipe); falls back to a stable descriptor for
+    a ruff-only self_check failure (sorted rule codes) or an opaque gate error."""
+    if phase == "self_check":
+        report = state.get("test_report") or {}
+        failures = (report.get("pytest") or {}).get("failures") or []
+        if failures:
+            f = failures[0]
+            return signature_for_failure(phase, f), f"{f.get('nodeid')}: {f.get('message')}"
+        codes = report.get("ruff_codes") or []
+        detail = "ruff findings: " + (", ".join(codes) or ((report.get("ruff") or {}).get("stdout") or "")[:400])
+        return compute_signature(phase, "ruff", "ruff", ",".join(sorted(codes)), ""), detail
+    if phase == "review":
+        review = state.get("review_result") or {}
+        blocking = review.get("blocking") or []
+        first = blocking[0] if blocking else {}
+        # A maker/checker stalemate is no-progress by another name (Â§3.4): sign the
+        # rejection by (location, severity) so a reviewer that keeps rejecting the
+        # same spot is caught by the same "same signature twice" rule.
+        sig = review_signature(first.get("location", ""), first.get("severity", ""))
+        detail = "review reject: " + "; ".join(
+            f"{f.get('severity')} {f.get('location')}: {f.get('rationale')}" for f in blocking[:3]
+        )
+        return sig, detail
+    # bdd_gate
+    report = state.get("bdd_report") or {}
+    failures = report.get("failures") or []
+    if failures:
+        f = failures[0]
+        return signature_for_failure(phase, f), f"{f.get('nodeid')}: {f.get('message')}"
+    stdout = report.get("stdout") or ""
+    return compute_signature(phase, "bdd", "bdd", template_message(stdout), ""), f"bdd_gate failed:\n{stdout[:400]}"
+
+
+def _diagnose_llm(state: CodingLoopState, phase: str, detail: str) -> tuple[str, str]:
+    """(category, insight) from the LLM, degrading gracefully: a structured-output
+    hiccup in diagnose must never crash the loop, so on failure we fall back to
+    an 'unknown' category (no free flake retry) and the code-only summary."""
+    try:
+        llm = _eng().get_llm("primary", temperature=0.0)
+        result = _eng()._llm_diagnose(llm, state, phase, detail)
+        return result.category, (result.insight or _summarize_failure(state))
+    except Exception:  # noqa: BLE001 -- diagnose is best-effort; a model/network hiccup here must not crash the loop
+        return "unknown", _summarize_failure(state)
+
+
+def _append_lesson(state: CodingLoopState, attempt: int, plan_id: str, signature: str,
+                   category: str, insight: str) -> list:
+    lessons = list(state.get("lessons", []))
+    lessons.append(
+        {
+            "attempt": attempt,
+            "plan_id": plan_id,
+            "failure_signature": signature,
+            "category": category,
+            "insight": insight,
+        }
+    )
+    return lessons
+
+
+def diagnose_node(state: CodingLoopState) -> dict:
+    """Classify the failure, sign it (Â§3.4), and decide retry / escalate.
+
+    Hard exits, in order (Â§3.4): stop flag; same signature twice in a row ->
+    active plan exhausted (in Phase 2 there's a single plan, so exhaustion ->
+    escalate; Phase 3 will route to a fresh plan and only escalate on the
+    second consecutive exhaustion); any budget breached -> escalate. A `flake`
+    classification buys a bounded number of free retries that don't burn an
+    attempt. Routing itself is pure code -- diagnose records `diagnosis.action`
+    and `_route_after_diagnose` reads it."""
+    if stop_flag_set(state["run_id"], _loop_state_dir()):
+        return {
+            "status": "escalated",
+            "escalation_reason": "stopped by user",
+            "diagnosis": {"action": "escalate"},
+        }
+
+    budgets = state["budgets"]
+    phase = _failed_phase(state) or "self_check"
+    signature, detail = _signature_and_detail(state, phase)
+    prev_signature = state.get("failure_signature")  # last attempt's, if any
+    category, insight = _diagnose_llm(state, phase, detail)
+
+    no_progress = prev_signature is not None and signature == prev_signature
+
+    # Flake: a bounded free retry that doesn't burn an attempt -- but never for
+    # a no-progress repeat (an identical failure twice isn't flakiness).
+    flake_free_retries = state.get("flake_free_retries", 0)
+    if category == "flake" and not no_progress and flake_free_retries < _MAX_FLAKE_FREE_RETRIES:
+        lessons = _append_lesson(state, state.get("attempt", 0), state.get("active_plan_id", "plan-1"),
+                                 signature, category, f"[flake, free retry] {insight}")
+        return {
+            "status": "coding",
+            "diagnosis": {"action": "retry", "category": category, "signature": signature, "flake": True},
+            "failure_signature": signature,
+            "prev_failure_signature": prev_signature,
+            "flake_free_retries": flake_free_retries + 1,
+            "lessons": lessons,
+        }
+
+    attempt = state.get("attempt", 0) + 1
+    total_attempts = state.get("total_attempts", 0) + 1
+    lessons = _append_lesson(state, attempt, state.get("active_plan_id", "plan-1"), signature, category, insight)
+
+    def _escalate(reason: str) -> dict:
+        return {
+            "status": "escalated",
+            "escalation_reason": reason,
+            "attempt": attempt,
+            "total_attempts": total_attempts,
+            "lessons": lessons,
+            "failure_signature": signature,
+            "prev_failure_signature": prev_signature,
+            "diagnosis": {"action": "escalate", "category": category, "signature": signature, "reason": reason},
+        }
+
+    elapsed = time.time() - state.get("run_started_at", time.time())
+    token_budget = budgets.get("token_budget", 0)
+    hard_budget = None
+    if elapsed > budgets["wall_clock_s"]:
+        hard_budget = "wall_clock"
+    elif total_attempts > budgets["max_total_attempts"]:
+        hard_budget = "max_total_attempts"
+    elif token_budget and state.get("tokens_used", 0) > token_budget:
+        # Token budget is a hard stop at this checkpoint, not a warning (Â§3.4).
+        hard_budget = "token_budget"
+
+    # 1-2. No progress: same signature twice -> active plan exhausted. If another
+    # candidate plan remains (and no hard budget is breached), switch to it via
+    # plan_tot -- the aggregated lessons steer the re-score (GoT). Escalate once
+    # two plans have been exhausted (Â§3.4 exit 2: a third built on the same
+    # lessons lands in the same place) or nothing else is left.
+    if no_progress:
+        exhausted = list(state.get("exhausted_plan_ids", []))
+        active = state.get("active_plan_id", "plan-1")
+        if active not in exhausted:
+            exhausted.append(active)
+        remaining = [p for p in (state.get("candidate_plans") or []) if p.get("id") not in exhausted]
+        if len(exhausted) >= 2 or not remaining or hard_budget:
+            base = _escalate(hard_budget or ("two_plans_exhausted" if len(exhausted) >= 2 else "no_progress"))
+            base["exhausted_plan_ids"] = exhausted
+            return base
+        return {
+            "status": "planning",
+            "exhausted_plan_ids": exhausted,
+            "attempt": 0,  # the fresh plan gets its own per-plan attempt budget
+            "total_attempts": total_attempts,
+            "lessons": lessons,
+            "failure_signature": signature,
+            "prev_failure_signature": prev_signature,
+            "diagnosis": {"action": "new_plan", "category": category, "signature": signature},
+        }
+
+    # 4. Budgets (token budget is a hard stop here when set; 0 means unlimited).
+    if hard_budget:
+        return _escalate(hard_budget)
+    if attempt > budgets["max_attempts_per_plan"]:
+        return _escalate("max_attempts_per_plan")
+
+    # Otherwise: the failure changed and there's budget left -> try again.
+    return {
+        "status": "coding",
+        "attempt": attempt,
+        "total_attempts": total_attempts,
+        "lessons": lessons,
+        "failure_signature": signature,
+        "prev_failure_signature": prev_signature,
+        "diagnosis": {"action": "retry", "category": category, "signature": signature},
+    }
+
+
+def _route_after_diagnose(state: CodingLoopState) -> str:
+    action = (state.get("diagnosis") or {}).get("action")
+    if action == "escalate":
+        return "escalate"
+    if action == "new_plan":  # Phase 3 -- plan switching
+        return "plan_tot"
+    return "code"
+
+
+def finalize_node(state: CodingLoopState) -> dict:
+    handle = _handle_from_state(state)
+    rev = worktree_commit(handle, f"coding-engineer: {state['goal'][:72]}")
+    report_path = write_run_report(state, _loop_state_dir(), outcome="done", commit_rev=rev)
+    return {"status": "done", "messages": [_status_message("finalize", True, note=f"report: {report_path}")]}
+
+
+def escalate_node(state: CodingLoopState) -> dict:
+    reason = state.get("escalation_reason") or "unknown"
+    rev = ""
+    if state.get("worktree_dir"):
+        handle = _handle_from_state(state)
+        rev = worktree_commit(handle, f"coding-engineer: WIP, escalated ({reason})")
+    report_path = write_run_report(state, _loop_state_dir(), outcome="escalated", commit_rev=rev)
+    return {"status": "escalated", "messages": [_status_message("escalate", False, note=f"{reason}; report: {report_path}")]}
\ No newline at end of file
diff --git a/coding_agent/state.py b/coding_agent/state.py
new file mode 100644
index 0000000..5bd91fd
--- /dev/null
+++ b/coding_agent/state.py
@@ -0,0 +1,130 @@
+"""State schema, budgets, and small shared helpers for the Coding Engineer loop.
+
+Extracted from ``coding_agent/engine.py`` during the single-responsibility
+refactor (CODING_ENGINEER.md Â§3.2).  These are the leaf definitions every
+other submodule builds on -- no LLM calls, no graph nodes, no subprocesses.
+"""
+
+from __future__ import annotations
+
+import os
+from pathlib import Path
+from typing import Annotated, TypedDict
+
+from langchain_core.messages import AIMessage
+from langgraph.graph.message import add_messages
+
+from coding_agent.tools.worktree import WorktreeHandle
+
+# Display/telemetry label for this agent. Defined here (not in app.py) so the
+# panel can import it without a circular dependency on app.py.
+CODING_ENGINEER_LABEL = "Coding Engineer"
+
+DEFAULT_BUDGETS: dict[str, int] = {
+    "max_attempts_per_plan": 3,
+    "max_plans": 3,
+    "max_total_attempts": 9,
+    "cmd_timeout_s": 120,
+    "wall_clock_s": 1800,
+    "token_budget": 0,
+}
+
+
+# ---------------------------------------------------------------------------
+# State schema (CODING_ENGINEER.md Â§3.2)
+#
+# Three fields were added during Phase 1 implementation that the original
+# plan didn't spell out a home for; see PHASED_PLAN.md "Deviations":
+#   - escalation_reason: escalate's reason needs to travel through state.
+#   - run_started_at: wall-clock budget needs a start time to compare against.
+#   - is_fallback_copy: finalize/escalate need to reconstruct a WorktreeHandle
+#     to commit/diff, and that dataclass field has to come from somewhere.
+# ---------------------------------------------------------------------------
+
+
+class Budgets(TypedDict):
+    max_attempts_per_plan: int
+    max_plans: int
+    max_total_attempts: int
+    cmd_timeout_s: int
+    wall_clock_s: int
+    token_budget: int
+
+
+class Plan(TypedDict):
+    id: str
+    steps: list[str]
+    rationale: str
+    score: float
+    status: str
+
+
+class Lesson(TypedDict):
+    attempt: int
+    plan_id: str
+    failure_signature: str | None
+    category: str | None  # added Phase 2 -- diagnose's LLM classification
+    insight: str
+
+
+class CodingLoopState(TypedDict, total=False):
+    # immutable per run
+    run_id: str
+    target_dir: str
+    worktree_dir: str
+    branch: str
+    is_fallback_copy: bool  # added in Phase 1 -- see module docstring
+    goal: str
+    budgets: Budgets
+    model_info: dict  # added in Phase 1 follow-up -- models.describe_all(), for the report/UI
+    # goal definition
+    spec: dict
+    feature_paths: list[str]
+    hitl_bdd_approval: bool
+    # planning
+    candidate_plans: list[Plan]
+    active_plan_id: str
+    lessons: list[Lesson]
+    # iteration
+    attempt: int
+    total_attempts: int
+    tokens_used: int  # Phase 4 -- best-effort running tally for the token budget (Â§3.4)
+    run_started_at: float  # added in Phase 1 -- see module docstring
+    last_diff: str
+    test_report: dict
+    bdd_report: dict
+    review_result: dict | None  # renamed from `review` -- can't share a name with the review node
+    escalation_reason: str | None  # added in Phase 1 -- see module docstring
+    # no-progress detection (Phase 2 -- CODING_ENGINEER.md Â§3.4)
+    failure_signature: str | None  # this attempt's signature
+    prev_failure_signature: str | None  # last attempt's, for the "same twice" check
+    exhausted_plan_ids: list[str]  # plans killed by no-progress
+    flake_free_retries: int  # free retries already spent on `flake` classifications
+    diagnosis: dict | None  # diagnose's per-attempt verdict incl. the routing action
+    # outcome + UI
+    status: str
+    messages: Annotated[list, add_messages]
+
+
+# ---------------------------------------------------------------------------
+# small helpers
+# ---------------------------------------------------------------------------
+
+
+def _loop_state_dir() -> Path:
+    return Path(os.getenv("CODING_AGENT_LOOP_DIR", ".loop"))
+
+
+def _status_message(node: str, ok: bool, note: str = "") -> AIMessage:
+    tag = "OK" if ok else "FAIL"
+    content = f"[{node}] {tag}" + (f" â€” {note}" if note else "")
+    return AIMessage(content=content, name=node)
+
+
+def _handle_from_state(state: CodingLoopState) -> WorktreeHandle:
+    return WorktreeHandle(
+        target_dir=Path(state["target_dir"]),
+        worktree_dir=Path(state["worktree_dir"]),
+        branch=state["branch"],
+        is_fallback_copy=state.get("is_fallback_copy", False),
+    )
\ No newline at end of file
```
