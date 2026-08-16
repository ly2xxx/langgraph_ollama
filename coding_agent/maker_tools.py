"""Maker tool construction for the Coding Engineer loop.

Extracted from ``coding_agent/engine.py`` during the single-responsibility
refactor.  Builds the filesystem/pytest tool surface the maker agent uses
and renders the task text fed to it.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.tools import tool

from coding_agent.prompts import MAKER_SYSTEM_PROMPT
from coding_agent.state import Budgets, CodingLoopState
from coding_agent.tools.code_exec import Jail, JailViolation, run_command


def _build_maker_tools(jail: Jail, budgets: Budgets) -> list:
    """Read/list/write/delete/move plus a scoped pytest runner. `run_command`
    supports more binaries than are exposed here (e.g. `git`, `ruff`) --
    self_check/bdd_gate already cover those; the maker doesn't need them
    directly. delete_file/move_file were added after Phase 1 shipped (see
    PHASED_PLAN.md "Phase 1 follow-up") once a real refactor-shaped goal
    (moving a module to a subfolder) showed write-only wasn't enough for a
    clean move -- the old path would just be left behind as a duplicate."""

    @tool
    def read_file(path: str) -> str:
        """Read a text file's contents. `path` is relative to the worktree root."""
        try:
            return jail.read_file(path)
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def list_dir(path: str = ".") -> str:
        """List a directory's entries. `path` is relative to the worktree root."""
        try:
            return "\n".join(jail.list_dir(path))
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Write (create or overwrite) a text file with the given full content.
        `path` is relative to the worktree root. Refuses frozen BDD feature files."""
        try:
            jail.write_file(path, content)
            return f"wrote {path}"
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def delete_file(path: str) -> str:
        """Delete a file. `path` is relative to the worktree root. Refuses
        frozen BDD feature files. Use this to remove a file after moving its
        content elsewhere with write_file -- write_file alone never deletes
        the original."""
        try:
            jail.delete_file(path)
            return f"deleted {path}"
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def move_file(src_path: str, dst_path: str) -> str:
        """Move/rename a file. Both paths are relative to the worktree root.
        Refuses the operation if either end is a frozen BDD feature file."""
        try:
            jail.move_file(src_path, dst_path)
            return f"moved {src_path} -> {dst_path}"
        except (JailViolation, OSError) as exc:
            return f"ERROR: {exc}"

    @tool
    def run_pytest(pytest_args: str = "") -> str:
        """Run pytest inside the worktree to check your work before finishing.
        `pytest_args` is an optional space-separated string of extra pytest arguments."""
        # Deliberately not named `args` -- pydantic's function-wrapping internals
        # (used by @tool's schema inference) reserve that name as a synthetic
        # field for wrapping Python's own *args, so a real parameter literally
        # named `args` silently gets renamed to `v__args` in the generated
        # schema, which the tool-calling model then can't satisfy. Confirmed
        # live: this was the exact "run_pytest() got an unexpected keyword
        # argument 'v__args'" failure from the first two live runs.
        extra = pytest_args.split() if pytest_args else []
        result = run_command("pytest", ["-q", *extra], cwd=jail.root, timeout_s=budgets["cmd_timeout_s"])
        return f"returncode={result.returncode}\n{result.stdout}\n{result.stderr}"

    return [read_file, list_dir, write_file, delete_file, move_file, run_pytest]


def _maker_task_text(state: CodingLoopState) -> str:
    spec = state.get("spec") or {}
    lessons = state.get("lessons") or []
    lesson_lines = "\n".join(f"- {lesson['insight']}" for lesson in lessons[-3:]) or "(none yet)"
    criteria = "\n".join(f"- {c}" for c in spec.get("acceptance_criteria", [])) or "(none extracted)"
    return (
        f"Goal: {state['goal']}\n\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        f"Frozen BDD scenarios (do not edit): {', '.join(state.get('feature_paths', [])) or '(none)'}\n\n"
        f"Recent lessons from earlier attempts:\n{lesson_lines}\n\n"
        "Make the smallest change that could make the tests pass. You may read files, "
        "list directories, write files, delete files, move/rename files, and run pytest "
        "to check your work. If you move something, delete the original -- write_file "
        "alone does not remove it."
    )