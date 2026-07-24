"""Unit tests for coding_agent.tools.code_exec — the filesystem jail and
allowlisted command runner. See CODING_ENGINEER.md §4 (Safety rails)."""

from pathlib import Path

import pytest

from coding_agent.tools.code_exec import (
    CommandRejected,
    Jail,
    JailViolation,
    run_command,
)


@pytest.fixture
def jail(tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    (root / "features").mkdir()
    (root / "features" / "calculator.feature").write_text("Feature: stub\n")
    return Jail(root=root, frozen=frozenset({Path("features/calculator.feature")}))


# -- path containment --------------------------------------------------------


def test_write_inside_worktree_succeeds(jail):
    jail.write_file("src/calculator.py", "def add(x): return x\n")
    assert (jail.root / "src" / "calculator.py").read_text() == "def add(x): return x\n"


def test_write_escapes_worktree_is_blocked(jail):
    with pytest.raises(JailViolation):
        jail.write_file("../../outside.txt", "pwned")


def test_absolute_path_escape_is_blocked(jail, tmp_path):
    outside = tmp_path / "outside.txt"
    with pytest.raises(JailViolation):
        jail.write_file(str(outside), "pwned")


def test_symlink_escape_is_blocked(jail, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = jail.root / "link_to_outside.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported/permitted on this platform")
    with pytest.raises(JailViolation):
        jail.write_file("link_to_outside.txt", "pwned")


def test_read_and_delete_of_non_frozen_file_succeeds(jail):
    jail.write_file("scratch.txt", "hello")
    assert jail.read_file("scratch.txt") == "hello"
    jail.delete_file("scratch.txt")
    assert not (jail.root / "scratch.txt").exists()


def test_list_dir(jail):
    jail.write_file("a.txt", "1")
    jail.write_file("b.txt", "2")
    assert jail.list_dir(".") == sorted(["a.txt", "b.txt", "features"])


# -- frozen set ---------------------------------------------------------------


def test_write_to_frozen_file_is_blocked_and_surfaced(jail):
    with pytest.raises(JailViolation, match="frozen"):
        jail.write_file("features/calculator.feature", "Feature: rewritten to cheat\n")


def test_apply_patch_to_frozen_file_is_blocked(jail):
    with pytest.raises(JailViolation, match="frozen"):
        jail.apply_patch("features/calculator.feature", "Feature: rewritten to cheat\n")


def test_delete_frozen_file_is_blocked(jail):
    with pytest.raises(JailViolation, match="frozen"):
        jail.delete_file("features/calculator.feature")


def test_move_frozen_file_away_is_blocked(jail):
    with pytest.raises(JailViolation, match="frozen"):
        jail.move_file("features/calculator.feature", "features/moved.feature")


def test_move_onto_frozen_path_is_blocked(jail):
    jail.write_file("scratch.feature", "Feature: not frozen\n")
    with pytest.raises(JailViolation, match="frozen"):
        jail.move_file("scratch.feature", "features/calculator.feature")


def test_git_internals_always_frozen_even_if_not_listed(jail):
    (jail.root / ".git").mkdir()
    with pytest.raises(JailViolation, match=r"\.git"):
        jail.write_file(".git/config", "[core]\n")


# -- run_command allowlist ----------------------------------------------------


def test_disallowed_binary_is_rejected(tmp_path):
    with pytest.raises(CommandRejected):
        run_command("bash", ["-c", "echo hi"], cwd=tmp_path, timeout_s=5)


def test_git_disallowed_subcommand_is_rejected(tmp_path):
    with pytest.raises(CommandRejected):
        run_command("git", ["push"], cwd=tmp_path, timeout_s=5)


def test_git_allowed_subcommand_runs(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    result = run_command("git", ["status"], cwd=tmp_path, timeout_s=5)
    assert result.returncode == 0
    assert not result.timed_out


def test_git_forbidden_flag_before_subcommand_is_rejected(tmp_path):
    with pytest.raises(CommandRejected):
        run_command("git", ["-c", "core.editor=vim", "status"], cwd=tmp_path, timeout_s=5)


def test_git_forbidden_flag_after_subcommand_is_rejected(tmp_path):
    with pytest.raises(CommandRejected):
        run_command("git", ["log", "--exec=whoami"], cwd=tmp_path, timeout_s=5)


def test_python_pip_install_blocked_by_default(tmp_path):
    with pytest.raises(CommandRejected):
        run_command("python", ["-m", "pip", "install", "requests"], cwd=tmp_path, timeout_s=5)


def test_python_pip_allowed_when_flag_set(tmp_path):
    result = run_command(
        "python", ["-m", "pip", "--version"], cwd=tmp_path, timeout_s=10, allow_install=True
    )
    assert not result.timed_out
    assert result.returncode == 0


def test_run_command_uses_given_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("here")
    result = run_command(
        "python", ["-c", "import os; print(os.listdir('.'))"], cwd=tmp_path, timeout_s=10
    )
    assert result.returncode == 0
    assert "marker.txt" in result.stdout


def test_command_timeout_is_enforced(tmp_path):
    result = run_command(
        "python", ["-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout_s=1
    )
    assert result.timed_out
    assert result.returncode != 0
