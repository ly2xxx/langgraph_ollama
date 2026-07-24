"""Jailed file tools and allowlisted command runner for the Coding Engineer
agent.

Every mutating filesystem operation and every subprocess invocation the
maker/checker agents can trigger funnels through this module. See
CODING_ENGINEER.md §4 (Safety rails) for the threat model this implements:

- Path containment via `os.path.realpath` (symlink-proof) + `is_relative_to`,
  not `Path.resolve()` alone.
- A frozen set (BDD feature files, `.git` internals) that blocks write,
  patch, delete, *and* move/rename — not just write.
- Violations are always raised, never silently swallowed: the error text is
  learning signal for the maker, and silent blocks hide bugs.
- `run_command` allowlists binaries, and for `git` specifically, subcommands
  and forbidden flags — `git` can do almost anything, so the binary
  allowlist alone isn't enough.
- Every subprocess call is `cwd`-pinned to the worktree with a sanitised
  environment, list-args, `shell=False`.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class JailViolation(Exception):
    """A tool call tried to touch a path outside the worktree, or a frozen
    path inside it. Always propagated to the caller."""


class CommandRejected(Exception):
    """`run_command` was asked to run a binary, subcommand, or flag that
    isn't on the allowlist."""


# ---------------------------------------------------------------------------
# Filesystem jail
# ---------------------------------------------------------------------------


@dataclass
class Jail:
    """Resolves and validates paths against a worktree root plus a frozen set.

    Parameters
    ----------
    root:
        The worktree directory. All file tool operations are confined here.
    frozen:
        Paths (relative to root) that may be read but never written,
        patched, deleted, or moved — e.g. the BDD feature files, once
        `author_bdd` has drafted them. A frozen entry that names a
        directory freezes everything under it.
    """

    root: Path
    frozen: frozenset[Path] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        self.root = Path(os.path.realpath(self.root))
        self.frozen = frozenset(Path(p) for p in self.frozen)

    # -- resolution ----------------------------------------------------

    def resolve(self, relative_path: str) -> Path:
        """Resolve `relative_path` against root and verify it stays inside.

        Uses `os.path.realpath` (not `Path.resolve()`) so symlinks are
        followed on both POSIX and Windows *before* the containment check —
        a symlink inside the worktree that points outside it must not be
        usable to escape the jail.
        """
        candidate = Path(relative_path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        real = Path(os.path.realpath(candidate))
        if not self._is_relative_to(real, self.root):
            raise JailViolation(
                f"path escapes worktree: {relative_path!r} resolved to "
                f"{real}, which is outside {self.root}"
            )
        return real

    @staticmethod
    def _is_relative_to(path: Path, other: Path) -> bool:
        try:
            path.relative_to(other)
            return True
        except ValueError:
            return False

    def _check_frozen(self, real_path: Path, op: str) -> None:
        try:
            rel = real_path.relative_to(self.root)
        except ValueError:
            rel = real_path

        # .git internals are always frozen, even if never explicitly listed.
        if rel.parts and rel.parts[0] == ".git":
            raise JailViolation(f"{op} refused: {rel} is inside .git, which is always frozen")

        for frozen_rel in self.frozen:
            if rel == frozen_rel or self._is_relative_to(real_path, self.root / frozen_rel):
                raise JailViolation(f"{op} refused: {rel} is frozen and cannot be modified")

    # -- file tools ------------------------------------------------------

    def read_file(self, relative_path: str) -> str:
        real = self.resolve(relative_path)
        return real.read_text(encoding="utf-8")

    def list_dir(self, relative_path: str = ".") -> list[str]:
        real = self.resolve(relative_path)
        return sorted(p.name for p in real.iterdir())

    def write_file(self, relative_path: str, content: str) -> None:
        real = self.resolve(relative_path)
        self._check_frozen(real, "write")
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(content, encoding="utf-8")

    def apply_patch(self, relative_path: str, patched_content: str) -> None:
        """Whole-file replace for v1. A real unified-diff patcher is a
        Phase-1+ refinement (smaller diffs, better for the reviewer to
        read) — the jail semantics are identical either way, so it's a
        drop-in swap later."""
        self.write_file(relative_path, patched_content)

    def delete_file(self, relative_path: str) -> None:
        real = self.resolve(relative_path)
        self._check_frozen(real, "delete")
        real.unlink()

    def move_file(self, src_relative: str, dst_relative: str) -> None:
        src = self.resolve(src_relative)
        dst = self.resolve(dst_relative)
        # Both endpoints go through the frozen check: moving a frozen file
        # away, or moving a new file ONTO a frozen path, are both refused.
        self._check_frozen(src, "move (source)")
        self._check_frozen(dst, "move (destination)")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)


# ---------------------------------------------------------------------------
# Allowlisted command runner
# ---------------------------------------------------------------------------

_ALLOWED_BINARIES = {"pytest", "ruff", "python", "git"}

_GIT_SUBCOMMAND_ALLOWLIST = {"status", "diff", "add", "commit", "log", "rev-parse"}

# Flags/values that are never permitted, regardless of subcommand, because
# they let git run arbitrary commands or rewrite its own config/hooks.
_GIT_FORBIDDEN_FLAG_PREFIXES = (
    "-c",
    "--exec",
    "--upload-pack",
    "--receive-pack",
    "--hooks-path",
    "--config",
    "core.hookspath",
)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _check_git_args(args: list[str]) -> None:
    if not args:
        raise CommandRejected("git: no subcommand given")
    subcommand = args[0]
    if subcommand not in _GIT_SUBCOMMAND_ALLOWLIST:
        raise CommandRejected(
            f"git subcommand {subcommand!r} is not on the allowlist "
            f"({sorted(_GIT_SUBCOMMAND_ALLOWLIST)})"
        )
    for arg in args:
        for forbidden in _GIT_FORBIDDEN_FLAG_PREFIXES:
            if arg == forbidden or arg.startswith(forbidden):
                raise CommandRejected(f"git argument {arg!r} is never permitted")


def run_command(
    binary: str,
    args: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    allow_install: bool = False,
) -> CommandResult:
    """Run an allowlisted binary as a list-args subprocess, jailed to `cwd`.

    Never uses `shell=True`. `cwd` is always the worktree — never
    inherited — and the environment is stripped down to a minimal set of
    variables needed to resolve and run the binary.
    """
    if binary not in _ALLOWED_BINARIES:
        raise CommandRejected(f"binary {binary!r} is not on the allowlist ({sorted(_ALLOWED_BINARIES)})")

    if binary == "git":
        _check_git_args(args)

    if binary == "python" and not allow_install and "pip" in args:
        raise CommandRejected(
            "pip invocations are blocked; set allow_install=True "
            "(CODING_AGENT_ALLOW_INSTALL=true) to permit them"
        )

    env = {
        "PATH": os.environ.get("PATH", ""),
        # Windows needs SYSTEMROOT to resolve DLLs for the Python launcher
        # and other binaries; harmless elsewhere.
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }

    try:
        proc = subprocess.run(
            [binary, *args],
            cwd=str(cwd),
            timeout=timeout_s,
            capture_output=True,
            text=True,
            env=env,
            shell=False,
            check=False,
        )
        return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
        return CommandResult(
            returncode=-1,
            stdout=stdout,
            stderr=f"command timed out after {timeout_s}s",
            timed_out=True,
        )
