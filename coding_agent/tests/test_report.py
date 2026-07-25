"""Unit tests for coding_agent.report's render_report -- specifically the
"## Models" section added so a run's resolved primary/secondary model is
logged in the audit trail, not just visible transiently in the UI/CLI at
start-of-run."""

from coding_agent.report import render_report


def _base_state(**overrides) -> dict:
    state = {
        "run_id": "run-1",
        "goal": "do a thing",
        "target_dir": "/tmp/target",
        "branch": "coding-engineer/run-1",
        "total_attempts": 1,
        "budgets": {"max_total_attempts": 4},
        "spec": {"acceptance_criteria": ["a thing happens"]},
        "feature_paths": ["features/thing.feature"],
        "test_report": {"passed": True},
        "bdd_report": {"passed": True},
        "lessons": [],
        "last_diff": "",
    }
    state.update(overrides)
    return state


def test_render_report_includes_models_section_when_present():
    model_info = {
        "primary": {"provider": "ollama", "model": "glm-5.2:cloud", "base_url": "http://localhost:11434"},
        "secondary": {"provider": "ollama", "model": "qwen3:14b", "base_url": "http://localhost:11434"},
    }
    report = render_report(_base_state(model_info=model_info), outcome="done", commit_rev="abc123")

    assert "## Models" in report
    assert "provider=ollama model=glm-5.2:cloud" in report
    assert "provider=ollama model=qwen3:14b" in report


def test_render_report_omits_models_section_when_absent():
    """Older/mocked states (e.g. the integration tests, which drive the
    graph directly rather than through stream_run) won't have model_info --
    the section should just be skipped, not raise or print 'None'."""
    report = render_report(_base_state(), outcome="done", commit_rev="abc123")

    assert "## Models" not in report
