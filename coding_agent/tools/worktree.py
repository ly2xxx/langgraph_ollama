"""Git worktree lifecycle helpers for the Coding Engineer agent.

Every run gets an isolated checkout on its own branch — a real `git
worktree` for git targets, or a temp-directory copy with a fresh throwaway
repo for non-git targets — so the loop's edits can never touch the user's
checkout directly. See CODING_ENGINEER.md §3.3 (intake) and §4 (Blast
radius).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(Exception):
    """Worktree setup, diff, commit, or cleanup failed."""


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


def _is_git_repo(path: Path) -> bool:
    if not path.exists():
        return False
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return result.returncode == 0 and result.stdout.strip() == "true"


@dataclass
class WorktreeHandle:
    target_dir: Path  # original target the run was pointed at
    worktree_dir: Path  # isolated checkout the loop actually works in
    branch: str
    is_fallback_copy: bool  # True if target wasn't a git repo


def create_worktree(target_dir: Path, run_id: str, loop_state_dir: Path) -> WorktreeHandle:
    """Create an isolated checkout for `run_id`.

    If `target_dir` is inside a git repo, uses `git worktree add` on a new
    branch `coding-engineer/<run_id>` off the current HEAD — the worktree
    shares the target repo's `.git`, so it inherits identity config
    (`user.name`/`user.email`) automatically.

    Otherwise falls back to copying `target_dir` into
    `loop_state_dir/worktrees/<run_id>` and `git init`-ing it there (with
    an agent-scoped identity, since a non-repo target has no config to
    inherit), so the rest of the loop (diff, commit) has a uniform git
    interface regardless of what the target looked like. This branch is
    never merged anywhere — the fallback repo only exists so
    self_check/bdd_gate/review have something to diff against.
    """
    target_dir = Path(target_dir)
    branch = f"coding-engineer/{run_id}"
    worktrees_root = Path(loop_state_dir) / "worktrees"
    worktrees_root.mkdir(parents=True, exist_ok=True)
    worktree_dir = worktrees_root / run_id

    if worktree_dir.exists():
        raise WorktreeError(f"worktree dir already exists: {worktree_dir}")

    if _is_git_repo(target_dir):
        result = _run_git(["worktree", "add", str(worktree_dir), "-b", branch], cwd=target_dir)
        if result.returncode != 0:
            raise WorktreeError(f"git worktree add failed: {result.stderr}")
        return WorktreeHandle(target_dir, worktree_dir, branch, is_fallback_copy=False)

    shutil.copytree(target_dir, worktree_dir)
    init = _run_git(["init", "-q", "-b", branch], cwd=worktree_dir)
    if init.returncode != 0:
        raise WorktreeError(f"git init failed on fallback copy: {init.stderr}")
    _run_git(["config", "user.email", "coding-agent@local"], cwd=worktree_dir)
    _run_git(["config", "user.name", "Coding Engineer Agent"], cwd=worktree_dir)
    _run_git(["add", "-A"], cwd=worktree_dir)
    commit_result = _run_git(
        ["commit", "-q", "--allow-empty", "-m", "coding-engineer: baseline (non-git target)"],
        cwd=worktree_dir,
    )
    if commit_result.returncode != 0:
        raise WorktreeError(f"baseline commit failed on fallback copy: {commit_result.stderr}")
    return WorktreeHandle(target_dir, worktree_dir, branch, is_fallback_copy=True)


def diff(handle: WorktreeHandle) -> str:
    """Diff against HEAD, including brand-new (untracked) files.

    `git diff HEAD` alone only shows tracked-and-modified paths; a new file
    the maker just wrote wouldn't appear at all. `add -A -N` (intent-to-add)
    records new paths in the index without staging their content, so they
    show up as additions in the diff. `commit()` re-stages everything with
    a real `add -A` afterwards, so this has no lasting effect on what gets
    committed.
    """
    intent = _run_git(["add", "-A", "-N"], cwd=handle.worktree_dir)
    if intent.returncode != 0:
        raise WorktreeError(f"git add -N failed: {intent.stderr}")
    result = _run_git(["diff", "HEAD"], cwd=handle.worktree_dir)
    if result.returncode != 0:
        raise WorktreeError(f"git diff failed: {result.stderr}")
    return result.stdout


def commit(handle: WorktreeHandle, message: str) -> str:
    """Stage everything and commit. Returns the new commit hash, or ''
    if there was nothing to commit."""
    add = _run_git(["add", "-A"], cwd=handle.worktree_dir)
    if add.returncode != 0:
        raise WorktreeError(f"git add failed: {add.stderr}")

    status = _run_git(["status", "--porcelain"], cwd=handle.worktree_dir)
    if not status.stdout.strip():
        return ""

    result = _run_git(["commit", "-q", "-m", message], cwd=handle.worktree_dir)
    if result.returncode != 0:
        raise WorktreeError(f"git commit failed: {result.stderr}")

    rev = _run_git(["rev-parse", "HEAD"], cwd=handle.worktree_dir)
    return rev.stdout.strip()


def cleanup(handle: WorktreeHandle) -> None:
    """Remove the worktree.

    For a real git-worktree checkout, uses `git worktree remove` (invoked
    from the original target repo) so git's own bookkeeping stays
    consistent; for a fallback copy, just deletes the directory. If the
    git-native removal fails for any reason, falls back to a filesystem
    delete plus `worktree prune` so a cleanup failure never blocks the loop
    from finishing.
    """
    if handle.is_fallback_copy:
        shutil.rmtree(handle.worktree_dir, ignore_errors=True)
        return

    result = _run_git(["worktree", "remove", "--force", str(handle.worktree_dir)], cwd=handle.target_dir)
    if result.returncode != 0:
        shutil.rmtree(handle.worktree_dir, ignore_errors=True)
        _run_git(["worktree", "prune"], cwd=handle.target_dir)
