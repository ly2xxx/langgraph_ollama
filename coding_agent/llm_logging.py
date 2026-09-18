"""Console tracing for every LLM and tool call, on either provider.

Attached inside get_llm(), so it covers ChatOllama and ChatOpenAI identically --
the two transports behave very differently and until now the only way to see
which one was in use, or what it returned, was the LiteLLM UI, which does not
exist for the native Ollama route at all.

Four things it surfaces that were invisible before, each of which cost a debugging
round at some point:

  provider/model/base_url   which transport actually served the call
  finish_reason             "length" means the response was TRUNCATED -- the
                            single most useful field, and absent from every log
                            we were reading
  tool_calls                a model that emits a tool call as prose shows up here
                            as "no tool calls" while its text looks like one
  tokens + duration         runaway generations, visible per call

Off switch: CODING_AGENT_LOG_LLM=0. Set it to 2 to also print prompt and response
previews.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

_TRUNCATED_REASONS = {"length", "max_tokens", "max_output_tokens"}


def log_level() -> int:
    """0 = off, 1 = one line per call (default), 2 = also preview content."""
    raw = os.getenv("CODING_AGENT_LOG_LLM")
    if raw is None or not raw.strip():
        return 1
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def _emit(line: str) -> None:
    # stderr so a caller piping stdout (the eval runner, a CLI) keeps clean output.
    print(line, file=sys.stderr, flush=True)


def _preview(text: Any, limit: int = 240) -> str:
    s = " ".join(str(text or "").split())
    return s[:limit] + ("…" if len(s) > limit else "")


def _finish_reason(message: Any) -> str | None:
    """Providers disagree on where this lives, and on what to call it."""
    meta = getattr(message, "response_metadata", None) or {}
    for key in ("finish_reason", "done_reason", "stop_reason"):
        if meta.get(key):
            return str(meta[key])
    return None


def _token_counts(response: Any, message: Any) -> tuple[int | None, int | None]:
    usage = getattr(message, "usage_metadata", None) or {}
    if usage:
        return usage.get("input_tokens"), usage.get("output_tokens")
    out = getattr(response, "llm_output", None) or {}
    tok = out.get("token_usage") or out.get("usage") or {}
    if tok:
        return (tok.get("prompt_tokens") or tok.get("input_tokens"),
                tok.get("completion_tokens") or tok.get("output_tokens"))
    return None, None


def _first_message(response: Any) -> Any:
    try:
        return response.generations[0][0].message
    except (AttributeError, IndexError):
        return None


class LLMConsoleLogger(BaseCallbackHandler):
    """One line out, one line back, per LLM call -- plus the maker's tool calls."""

    def __init__(self, role: str, provider: str, model: str | None, base_url: str | None):
        self.role = role
        self.provider = provider
        self.model = model or "?"
        self.base_url = base_url or "?"
        self._started: dict[Any, float] = {}
        self._tool_started: dict[Any, tuple[str, float]] = {}

    # ---- LLM ---------------------------------------------------------------
    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs):
        if not log_level():
            return
        self._started[run_id] = time.time()
        flat = [m for batch in (messages or []) for m in batch]
        chars = sum(len(str(getattr(m, "content", ""))) for m in flat)
        _emit(f"  [llm→] {self.role:9s} {self.provider}/{self.model} @ {self.base_url}  "
              f"{len(flat)} msg, {chars/1000:.1f}k chars")
        if log_level() >= 2 and flat:
            _emit(f"         prompt: {_preview(getattr(flat[-1], 'content', ''))}")

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        if not log_level():
            return
        elapsed = time.time() - self._started.pop(run_id, time.time())
        msg = _first_message(response)
        prompt_tok, completion_tok = _token_counts(response, msg)
        reason = _finish_reason(msg)
        calls = list(getattr(msg, "tool_calls", None) or [])

        bits = [f"{elapsed:.1f}s"]
        if prompt_tok is not None or completion_tok is not None:
            bits.append(f"{prompt_tok or '?'}→{completion_tok or '?'} tok")
        if reason:
            bits.append(f"finish={reason}")
        bits.append(f"{len(calls)} tool call(s)" if calls else "no tool calls")

        line = f"  [llm←] {self.role:9s} " + "  ".join(bits)
        if reason and reason.lower() in _TRUNCATED_REASONS:
            # The failure mode we spent days not seeing: output cut mid-JSON, so
            # nothing parses and the caller silently retries.
            line += "   ** TRUNCATED — raise CODING_AGENT_MAX_TOKENS or shrink the request **"
        _emit(line)

        for call in calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "?")
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
            _emit(f"         → {name}({_preview(args, 120)})")
        if log_level() >= 2 and msg is not None and not calls:
            _emit(f"         text: {_preview(getattr(msg, 'content', ''))}")

    def on_llm_error(self, error, *, run_id=None, **kwargs):
        if not log_level():
            return
        self._started.pop(run_id, None)
        _emit(f"  [llm✗] {self.role:9s} {type(error).__name__}: {_preview(error, 300)}")

    # ---- tools (fire when this handler is passed to the maker's invoke) -----
    def on_tool_start(self, serialized, input_str, *, run_id=None, **kwargs):
        if not log_level():
            return
        name = (serialized or {}).get("name", "?")
        self._tool_started[run_id] = (name, time.time())
        _emit(f"  [tool→] {name}  {_preview(input_str, 160)}")

    def on_tool_end(self, output, *, run_id=None, **kwargs):
        if not log_level():
            return
        name, started = self._tool_started.pop(run_id, ("?", time.time()))
        _emit(f"  [tool←] {name}  {time.time()-started:.1f}s  {_preview(output, 160)}")

    def on_tool_error(self, error, *, run_id=None, **kwargs):
        if not log_level():
            return
        name, _ = self._tool_started.pop(run_id, ("?", 0))
        _emit(f"  [tool✗] {name}  {type(error).__name__}: {_preview(error, 200)}")
