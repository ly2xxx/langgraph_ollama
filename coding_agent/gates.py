"""Quality-gate logic and differential linting for the Coding Engineer loop.

Extracted from ``coding_agent/engine.py`` during the single-responsibility
refactor.  Contains the ruff/pytest report readers, the differential
"new findings" computation, and the harness-exclusion helpers shared by
self_check / bdd_gate / author_bdd.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from coding_agent.signatures import extract_failures
from coding_agent.state import CodingLoopState
from coding_agent.tools.code_exec import run_command
from coding_agent.tools.worktree import (
    WorktreeHandle,
    file_at_baseline as worktree_file_at_baseline,
    renamed_paths as worktree_renamed_paths,
)


def _read_json_report(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("summary", {})


def _read_failures(path: Path) -> list[dict]:
    """Failing tests from a pytest-json-report file, normalised for signing
    (nodeid, error_class, message, top_frame_func) -- see signatures.py.
    Kept separate from _read_json_report (which returns only the summary, the
    Phase 1 shape) so the summary contract stays unchanged; diagnose (Phase 2)
    reads these to compute the failure_signature (§3.4)."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return extract_failures(data)


def _read_step_defs(state: CodingLoopState) -> str:
    """Concatenate the step-definition files under the frozen feature dirs, for
    the reviewer to audit for trivial-pass hacks (CODING_ENGINEER.md §3.3). The
    maker wrote these under a frozen .feature file, so they're the likeliest
    place a green run is actually cheating."""
    worktree_dir = Path(state["worktree_dir"])
    feature_dirs = {Path(fp).parent for fp in state.get("feature_paths", [])}
    chunks: list[str] = []
    for d in feature_dirs:
        base = worktree_dir / d
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            try:
                chunks.append(f"# {py.relative_to(worktree_dir)}\n{py.read_text(encoding='utf-8')}")
            except OSError:
                continue
    return "\n\n".join(chunks) or "(no step definitions found)"


def _harness_exclude_dirs(worktree_dir: Path) -> list[str]:
    """Directories self_check/bdd_gate should never recurse into, regardless
    of the target's own scope: the agent's own package, when the target
    happens to be (or contain) this repo -- e.g. when self-hosting the
    Coding Engineer on its own codebase, a goal about some other file has
    no business running coding_agent's ~40-test suite as a side effect.
    Only returned if actually present, so this is a no-op for any other
    target. Added after Phase 1 shipped -- see PHASED_PLAN.md "Phase 1
    follow-up"."""
    return ["coding_agent"] if (worktree_dir / "coding_agent").is_dir() else []


def _run_ruff_json(files: list[str], cwd: Path, harness_excludes: list[str], timeout: int):
    """Run `ruff check --select E9,F --output-format json` on `files`
    (relative to `cwd`) and return (findings, raw_result). `findings` is the
    parsed JSON list, or None if ruff's output couldn't be parsed (caller
    should then fall back to an opaque rc check). Empty list == clean.

    `--select E9,F` (syntax errors + pyflakes) rather than bare `ruff check`:
    self_check runs against an arbitrary target worktree whose own ruff config
    we don't control and shouldn't depend on -- an explicit, minimal, always-
    the-same selection keeps this a fast correctness check, not a style audit.

    `--per-file-ignores __init__.py:F401`: a package __init__.py that re-exports
    names (`from .mod import Thing`) trips F401 "imported but unused" -- but that
    IS the file's purpose, and it's a brand-new file with no baseline to forgive
    it against, so without this exception a maker creating a re-exporting package
    (exactly what the RAG POC does with rag_agent/__init__.py) would fail
    self_check on the single most conventional line in Python packaging. Scoped
    to F401 in __init__.py only; genuine syntax errors and other pyflakes issues
    there are still caught.
    """
    if not files:
        return [], None
    result = run_command(
        "ruff",
        ["check", *files, "--select", "E9,F", "--per-file-ignores", "__init__.py:F401",
         "--output-format", "json", *[f"--extend-exclude={d}" for d in harness_excludes]],
        cwd=cwd,
        timeout_s=timeout,
    )
    if result.timed_out:
        return None, result
    try:
        findings = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        return None, result
    return findings, result


def _ruff_new_findings(worktree_dir: Path, changed: list[str], handle: WorktreeHandle,
                       harness_excludes: list[str], timeout: int):
    """E9,F ruff findings the maker *introduced this run* -- current findings
    on the changed files, minus those already present in each file at the run's
    baseline (HEAD), compared per (relative-path, rule-code) so line shifts from
    the edit don't matter. Files the maker newly created have no baseline, so
    every finding in them counts (a brand-new file should be clean).

    Why this exists: scoping ruff to changed files (previous fix) still gated on
    pre-existing debt whenever the maker legitimately had to touch a file that
    already carried it -- the live run escalated 4x because app.py's import line
    genuinely needed updating for the module move, and app.py already had an
    unrelated duplicate `import os` (F811). The maker reported "all 6 BDD
    scenarios pass" every attempt, but self_check blocked before bdd_gate could
    confirm it. Forgiving pre-existing findings fixes that while still catching
    anything the maker actually breaks.

    Returns (new_findings, current_result). new_findings is None if ruff output
    couldn't be parsed at all (caller falls back to opaque rc)."""
    current, current_result = _run_ruff_json(changed, worktree_dir, harness_excludes, timeout)
    if current is None:
        return None, current_result
    if not current:
        return [], current_result

    # A moved file has no blob at its new path in HEAD; without this its
    # (pre-existing) content would all read as newly introduced. renamed_paths
    # lets us look the baseline up at the file's OLD path instead. Written into
    # tmp under the NEW path so the (relative-path, code) comparison key lines
    # up with the current findings.
    renames = worktree_renamed_paths(handle)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        baseline_files: list[str] = []
        for rel in changed:
            content = worktree_file_at_baseline(handle, rel)
            if content is None and rel in renames:
                content = worktree_file_at_baseline(handle, renames[rel])
            if content is None:
                continue  # genuinely new file this run -> no baseline; its findings all count
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            baseline_files.append(rel)
        baseline, _ = _run_ruff_json(baseline_files, tmp_path, [], timeout)
        baseline = baseline or []

    def _key(finding: dict, root: Path) -> tuple[str, str]:
        fname = finding.get("filename", "")
        try:
            rel = os.path.relpath(fname, root)
        except ValueError:
            rel = fname
        return (rel.replace(os.sep, "/"), finding.get("code") or "")

    baseline_counts = Counter(_key(f, tmp_path) for f in baseline)
    seen: Counter = Counter()
    new: list[dict] = []
    for f in current:
        k = _key(f, worktree_dir)
        seen[k] += 1
        if seen[k] > baseline_counts.get(k, 0):
            new.append(f)
    return new, current_result


def _render_ruff_findings(findings: list[dict]) -> str:
    """One line per finding for the run report (json output isn't human-facing)."""
    if not findings:
        return ""
    lines = []
    for f in findings:
        loc = f.get("location") or {}
        rel = f.get("filename", "?")
        lines.append(f"{rel}:{loc.get('row', '?')}:{loc.get('column', '?')} {f.get('code')} {f.get('message', '')}")
    return "\n".join(lines)


def _is_under_any(rel_path: str, dirs: set[str]) -> bool:
    """True if rel_path lives inside one of `dirs` (or is one of them)."""
    parts = Path(rel_path).parts
    for d in dirs:
        dparts = Path(d).parts
        if len(parts) >= len(dparts) and tuple(parts[: len(dparts)]) == dparts:
            return True
    return False