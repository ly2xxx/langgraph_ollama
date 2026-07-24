"""Unit tests for coding_agent.models — the primary/secondary model seam.

No network calls: only construction and env-var resolution are checked,
never `.invoke()`. See CODING_ENGINEER.md §3.5."""

import pytest

from coding_agent.models import UnknownProviderError, describe, get_llm


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "CODING_AGENT_PRIMARY_PROVIDER",
        "CODING_AGENT_PRIMARY_MODEL",
        "CODING_AGENT_PRIMARY_BASE_URL",
        "CODING_AGENT_SECONDARY_PROVIDER",
        "CODING_AGENT_SECONDARY_MODEL",
        "CODING_AGENT_SECONDARY_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_primary_defaults_to_ollama_provider(monkeypatch):
    monkeypatch.setenv("CODING_AGENT_PRIMARY_MODEL", "test-primary-model")
    monkeypatch.setenv("CODING_AGENT_PRIMARY_BASE_URL", "http://localhost:11434")
    cfg = describe("primary")
    assert cfg["provider"] == "ollama"
    assert cfg["model"] == "test-primary-model"
    assert cfg["base_url"] == "http://localhost:11434"


def test_secondary_falls_back_to_primary_when_unset(monkeypatch):
    monkeypatch.setenv("CODING_AGENT_PRIMARY_MODEL", "primary-model")
    monkeypatch.setenv("CODING_AGENT_PRIMARY_BASE_URL", "http://localhost:11434")
    cfg = describe("secondary")
    assert cfg["provider"] == "ollama"
    assert cfg["model"] == "primary-model"
    assert cfg["base_url"] == "http://localhost:11434"


def test_secondary_overrides_independently(monkeypatch):
    monkeypatch.setenv("CODING_AGENT_PRIMARY_MODEL", "primary-model")
    monkeypatch.setenv("CODING_AGENT_SECONDARY_MODEL", "secondary-model")
    cfg = describe("secondary")
    assert cfg["model"] == "secondary-model"
    # primary is unaffected by a secondary override.
    assert describe("primary")["model"] == "primary-model"


def test_get_llm_primary_constructs_chat_ollama(monkeypatch):
    monkeypatch.setenv("CODING_AGENT_PRIMARY_MODEL", "glm-5.2:cloud")
    monkeypatch.setenv("CODING_AGENT_PRIMARY_BASE_URL", "http://localhost:11434")
    llm = get_llm("primary")
    assert llm.model == "glm-5.2:cloud"


def test_get_llm_secondary_can_diverge_from_primary(monkeypatch):
    monkeypatch.setenv("CODING_AGENT_PRIMARY_MODEL", "model-a")
    monkeypatch.setenv("CODING_AGENT_SECONDARY_MODEL", "model-b")
    monkeypatch.setenv("CODING_AGENT_PRIMARY_BASE_URL", "http://localhost:11434")
    primary = get_llm("primary")
    secondary = get_llm("secondary")
    assert primary.model == "model-a"
    assert secondary.model == "model-b"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("CODING_AGENT_PRIMARY_PROVIDER", "bogus-provider")
    with pytest.raises(UnknownProviderError):
        get_llm("primary")
