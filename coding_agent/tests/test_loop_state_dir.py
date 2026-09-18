"""Where `.loop` lands.

Run artefacts (worktrees, state.json, run-report.md, checkpoints.db) used to go
under `.loop` relative to the *process CWD*, which meant they landed beside
whatever launched the run -- the CLI's directory, the FastAPI server's, or
Streamlit's -- and never anywhere near the repo being worked on. They now land
beside the target's git repo root instead.
"""

import subprocess

import pytest

from coding_agent.state import _loop_state_dir


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.delenv("CODING_AGENT_LOOP_DIR", raising=False)


@pytest.fixture
def sandbox(tmp_path):
    """tmp_path/sandbox/proj1 -- a git repo, mirroring H:/code/sandbox/proj1."""
    base = tmp_path / "sandbox"
    repo = base / "proj1"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return base, repo


def test_lands_beside_the_target_repo(sandbox):
    base, repo = sandbox
    assert _loop_state_dir(repo) == (base / ".loop").resolve()


def test_subdirectory_of_a_repo_still_anchors_on_the_repo_root(sandbox):
    """The target's own parent can be *inside* the repo, which would nest a git
    worktree in its own repo. Anchor on the repo root, not on the target."""
    base, repo = sandbox
    nested = repo / "services" / "api"
    nested.mkdir(parents=True)
    assert _loop_state_dir(nested) == (base / ".loop").resolve()


def test_non_git_target_anchors_on_the_target_itself(sandbox):
    base, _ = sandbox
    plain = base / "not-a-repo"
    plain.mkdir()
    assert _loop_state_dir(plain) == (base / ".loop").resolve()


def test_env_override_beats_the_target(sandbox, monkeypatch):
    base, repo = sandbox
    monkeypatch.setenv("CODING_AGENT_LOOP_DIR", str(base / "elsewhere"))
    assert _loop_state_dir(repo) == (base / "elsewhere").resolve()


def test_no_target_keeps_the_historical_cwd_behaviour(tmp_path, monkeypatch):
    """Callers with no target in hand (browsing past runs) get the old default
    rather than an error."""
    monkeypatch.chdir(tmp_path)
    assert _loop_state_dir() == (tmp_path / ".loop").resolve()


def test_unwritable_parent_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    """A repo at a filesystem root has no usable parent. Degrade to the old
    behaviour mid-run rather than raising."""
    monkeypatch.chdir(tmp_path)
    assert _loop_state_dir("/") == (tmp_path / ".loop").resolve()


def test_resolving_creates_nothing(sandbox):
    """GET /runs/{id} resolves this path on every poll; it must not litter a
    .loop next to the user's repo just to answer 'no report yet'."""
    base, repo = sandbox
    _loop_state_dir(repo)
    assert not (base / ".loop").exists()
