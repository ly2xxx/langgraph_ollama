"""Local folder browsing and validation, so a target can be picked in Swagger.

The agent works on a git worktree branched off the target's HEAD, so a target
that is not inside a git repo silently falls back to a copy. That is worth
telling the user before they start a 10-minute run, not after.
"""
from __future__ import annotations

import os
import string
import subprocess
from pathlib import Path

from fastapi import HTTPException

from api import settings

_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".loop",
         ".pytest_cache", ".ruff_cache", ".mypy_cache", ".idea", ".tox"}


def resolve(path: str) -> Path:
    """Resolve to an absolute real path, rejecting anything outside ALLOWED_ROOTS."""
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(400, f"cannot resolve path: {exc}") from exc
    if settings.ALLOWED_ROOTS and not any(
        p == root or root in p.parents for root in settings.ALLOWED_ROOTS
    ):
        raise HTTPException(
            403,
            f"path is outside the allowed roots ({settings.roots_description()})",
        )
    return p


def require_dir(path: str) -> Path:
    p = resolve(path)
    if not p.exists():
        raise HTTPException(404, f"no such path: {p}")
    if not p.is_dir():
        raise HTTPException(400, f"not a directory: {p}")
    return p


def git_root(path: Path) -> Path | None:
    """The repo root containing `path`, or None if it is not inside a git repo."""
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def dirty_files(path: Path) -> list[str]:
    """Uncommitted paths. The worktree is cut from HEAD, so these are NOT seen
    by the agent -- a common and confusing surprise, surfaced up front."""
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    return [ln[3:].strip() for ln in r.stdout.splitlines() if ln.strip()][:50]


def roots() -> list[str]:
    """Sensible starting points for browsing."""
    if settings.ALLOWED_ROOTS:
        return [str(p) for p in settings.ALLOWED_ROOTS]
    out = [str(Path.cwd()), str(Path.home())]
    if os.name == "nt":  # Windows: offer the drives that actually exist
        out += [f"{letter}:\\" for letter in string.ascii_uppercase
                if Path(f"{letter}:\\").exists()]
    else:
        out.append("/")
    seen, unique = set(), []
    for p in out:
        if p not in seen:
            seen.add(p); unique.append(p)
    return unique


def list_children(path: Path, include_hidden: bool = False) -> list[dict]:
    """Immediate subdirectories, each flagged with whether it is a git repo."""
    try:
        entries = sorted(
            (e for e in path.iterdir() if e.is_dir()),
            key=lambda e: e.name.lower(),
        )
    except PermissionError as exc:
        raise HTTPException(403, f"permission denied: {path}") from exc
    out = []
    for e in entries:
        if e.name in _SKIP:
            continue
        if not include_hidden and e.name.startswith("."):
            continue
        out.append({
            "name": e.name,
            "path": str(e),
            "is_git_repo": (e / ".git").exists(),
        })
    return out
