"""Unit tests for coding_agent.tools.worktree — the isolation layer that
gives every run its own branch (or, for non-git targets, its own throwaway
repo). See CODING_ENGINEER.md §3.3 (intake) and §4 (Blast radius)."""

import subprocess

import pytest

from coding_agent.tools.worktree import (
    WorktreeError,
    cleanup,
    commit,
    create_worktree,
    diff,
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture
def git_target(tmp_path):
    target = tmp_path / "target-repo"
    target.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=target)
    _git(["config", "user.email", "test@example.com"], cwd=target)
    _git(["config", "user.name", "Test"], cwd=target)
    (target / "README.md").write_text("hello\n")
    _git(["add", "-A"], cwd=target)
    _git(["commit", "-q", "-m", "init"], cwd=target)
    return target


@pytest.fixture
def loop_state_dir(tmp_path):
    d = tmp_path / ".loop"
    d.mkdir()
    return d


def test_create_worktree_from_git_target_round_trips(git_target, loop_state_dir):
    handle = create_worktree(git_target, "run-1", loop_state_dir)
    assert handle.worktree_dir.exists()
    assert handle.branch == "coding-engineer/run-1"
    assert not handle.is_fallback_copy
    cleanup(handle)
    assert not handle.worktree_dir.exists()


def test_worktree_diff_and_commit_on_git_target(git_target, loop_state_dir):
    handle = create_worktree(git_target, "run-2", loop_state_dir)
    (handle.worktree_dir / "new_file.py").write_text("print('hi')\n")

    d = diff(handle)
    assert "new_file.py" in d

    rev = commit(handle, "coding-engineer: add new_file.py")
    assert rev  # non-empty commit hash

    # original target repo is never touched by loop commits.
    assert not (git_target / "new_file.py").exists()
    cleanup(handle)


def test_commit_with_no_changes_returns_empty(git_target, loop_state_dir):
    handle = create_worktree(git_target, "run-3", loop_state_dir)
    rev = commit(handle, "no-op")
    assert rev == ""
    cleanup(handle)


def test_create_worktree_from_non_git_target_falls_back(tmp_path, loop_state_dir):
    target = tmp_path / "plain-target"
    target.mkdir()
    (target / "calculator.py").write_text("def add(x): return 0\n")

    handle = create_worktree(target, "run-4", loop_state_dir)
    assert handle.is_fallback_copy
    assert (handle.worktree_dir / "calculator.py").exists()
    # target itself was never touched -- no .git created there.
    assert not (target / ".git").exists()

    d = diff(handle)
    assert d == ""  # baseline commit means nothing to diff yet against HEAD

    (handle.worktree_dir / "calculator.py").write_text("def add(x): return x\n")
    rev = commit(handle, "implement add")
    assert rev

    cleanup(handle)
    assert not handle.worktree_dir.exists()


def test_duplicate_run_id_raises(git_target, loop_state_dir):
    handle = create_worktree(git_target, "run-5", loop_state_dir)
    with pytest.raises(WorktreeError):
        create_worktree(git_target, "run-5", loop_state_dir)
    cleanup(handle)
