"""Primary / secondary model configuration for the Coding Engineer agent.

Every LLM-calling node goes through `get_llm(role)` — never constructs a
chat model directly — so pointing the checker at a different model, or
moving off Ollama entirely, is a config change here, not a rewrite of
every node's call site. See CODING_ENGINEER.md §3.5.

Roles:
    primary   — intake, author_bdd, plan_tot propose, code/maker, diagnose.
                The high-frequency, in-the-loop calls.
    secondary — plan_tot judge, review/checker. The independent-judgement
                calls, deliberately capable of being a *different* model.
                Falls back to the primary config wherever a SECONDARY_*
                variable isn't set, so the loop works with one model and
                sharpens with two.
"""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

Role = Literal["primary", "secondary"]


class UnknownProviderError(Exception):
    """A `*_PROVIDER` env var named a provider with no branch in
    `get_llm`."""


def _env(role: str, suffix: str) -> str | None:
    return os.getenv(f"CODING_AGENT_{role.upper()}_{suffix}")


def _resolve_role_config(role: Role) -> dict[str, str | None]:
    if role == "secondary":
        provider = _env("secondary", "PROVIDER") or _env("primary", "PROVIDER") or "ollama"
        model = _env("secondary", "MODEL") or _env("primary", "MODEL") or os.getenv("OLLAMA_MODEL")
        base_url = _env("secondary", "BASE_URL") or _env("primary", "BASE_URL") or os.getenv("OLLAMA_BASE_URL")
    else:
        provider = _env("primary", "PROVIDER") or "ollama"
        model = _env("primary", "MODEL") or os.getenv("OLLAMA_MODEL")
        base_url = _env("primary", "BASE_URL") or os.getenv("OLLAMA_BASE_URL")
    return {"provider": provider, "model": model, "base_url": base_url}


def describe(role: Role) -> dict[str, str | None]:
    """Non-secret debug view of what a role currently resolves to — used by
    the UI / run report so a run is auditable without re-deriving env-var
    precedence by hand."""
    return _resolve_role_config(role)


def describe_all() -> dict[str, dict[str, str | None]]:
    """`describe()` for both roles at once -- the single call site the CLI,
    the panel, and the run report all go through, so "what model is this
    run using" is answered the same way everywhere instead of three
    hand-rolled dict-building spots drifting apart."""
    return {"primary": describe("primary"), "secondary": describe("secondary")}


def get_llm(role: Role, *, temperature: float = 0.0):
    """Return a chat model for the given role.

    Today only the 'ollama' provider is implemented; the branch below is
    the seam a future provider (openai, anthropic, ...) plugs into without
    touching any node's call site.
    """
    config = _resolve_role_config(role)
    provider = config["provider"]

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config["model"],
            base_url=config["base_url"],
            temperature=temperature,
        )

    raise UnknownProviderError(
        f"unknown provider {provider!r} for role {role!r} — add a branch "
        "in coding_agent/models.py to support it"
    )
