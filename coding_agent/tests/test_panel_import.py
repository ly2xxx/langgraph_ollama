"""Smoke test for the Streamlit panel wiring (Phase 4). Doesn't render -- just
proves the module imports and its public entry point + label constant exist, so
a refactor in engine.py that breaks the panel's imports fails a test rather than
only surfacing when someone opens the app."""

import pytest


def test_panel_imports_and_exposes_entry_point():
    pytest.importorskip("streamlit")
    from ui import coding_engineer_panel

    assert callable(coding_engineer_panel.render_coding_engineer_panel)
    assert coding_engineer_panel.DEMO_GOALS  # demo goals present


def test_coding_engineer_label_constant():
    from coding_agent.engine import CODING_ENGINEER_LABEL

    assert CODING_ENGINEER_LABEL == "Coding Engineer"


def test_model_overrides_set_env(monkeypatch):
    pytest.importorskip("streamlit")
    from ui import coding_engineer_panel as panel

    monkeypatch.delenv("CODING_AGENT_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("CODING_AGENT_SECONDARY_MODEL", raising=False)

    panel._apply_model_overrides("my-primary", "my-secondary")
    import os

    assert os.environ["CODING_AGENT_PRIMARY_MODEL"] == "my-primary"
    assert os.environ["CODING_AGENT_SECONDARY_MODEL"] == "my-secondary"

    # blank fields must NOT clobber an existing/env value
    panel._apply_model_overrides("", "")
    assert os.environ["CODING_AGENT_PRIMARY_MODEL"] == "my-primary"
