"""Robust structured-output invocation for the Coding Engineer's LLM calls.

Why this exists: the first live run of the agent (see PHASED_PLAN.md,
"Phase 1 follow-up — live-run fixes") failed with an OutputParserException
in `intake` — the model produced a perfectly good spec, but formatted as
markdown instead of JSON, and the default `with_structured_output` parser
(tool-calling based) crashed the whole graph. This was the exact
"local-model structured-output brittleness" risk CODING_ENGINEER.md §7
called out, with a promised mitigation ("one retry with the error fed
back") that Phase 1 hadn't actually implemented. Now it is, plus one
better layer in front:

1. Prefer `method="json_schema"` — langchain-ollama routes the schema
   through Ollama's native `format` parameter, which *constrains decoding*
   to schema-valid JSON. The model cannot produce markdown prose even if
   it wants to. (Verified available on langchain-ollama 0.3.x.)
2. Fall back to the default tool-calling method if json_schema isn't
   supported by the installed provider/model.
3. On any parse failure, retry once with the parse error appended to the
   prompt and an explicit "ONLY valid JSON" instruction.
4. If everything fails, raise `StructuredOutputError` — callers (intake,
   author_bdd) catch this and escalate the run gracefully with a report,
   rather than letting the raw exception blow up the graph and surface as
   a stack trace in the UI.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: your previous response could not be parsed as structured output "
    "(error: {error}). Respond with ONLY a single valid JSON object matching the "
    "required schema -- properly escape all newlines as \\n inside multi-line string values. "
    "No markdown formatting, no code fences, no commentary. Just the raw JSON object."
)

# Methods to try, in order. json_schema constrains Ollama's decoder to the
# schema (most reliable); function_calling is langchain's default and works
# across providers.
_METHODS = ("json_schema", "function_calling")


class StructuredOutputError(Exception):
    """All methods and retries failed to produce parseable structured output.

    Carries the last underlying error; callers should escalate the run with
    this message rather than crash."""


def invoke_structured(llm, schema: type[SchemaT], prompt: str, retries_per_method: int = 1) -> SchemaT:  # noqa: UP047 -- PEP 695 syntax would break older interpreters some CI/dev envs still run
    """Invoke `llm` for a `schema`-shaped structured response, robustly.

    Tries each method in `_METHODS`; within a method, retries up to
    `retries_per_method` extra times, feeding the parse error back into the
    prompt. Raises StructuredOutputError only when every combination fails.
    """
    last_error: Exception | None = None

    for method in _METHODS:
        try:
            structured = llm.with_structured_output(schema, method=method)
        except Exception as exc:  # noqa: BLE001 -- any failure here means "method unsupported"; falling through is the point
            last_error = exc
            continue

        attempt_prompt = prompt
        for _ in range(1 + retries_per_method):
            try:
                result = structured.invoke(attempt_prompt)
            except Exception as exc:  # noqa: BLE001 -- absorbing arbitrary provider/parser errors is this wrapper's job
                last_error = exc
                attempt_prompt = prompt + _RETRY_SUFFIX.format(error=str(exc)[:500])
                continue
            if result is None:
                # Some providers return None instead of raising when the
                # model's output couldn't be bound to the schema.
                last_error = ValueError(f"structured output returned None for method={method!r}")
                attempt_prompt = prompt + _RETRY_SUFFIX.format(error="model returned no parseable object")
                continue
            return result

    raise StructuredOutputError(
        f"structured output failed for schema {schema.__name__} after trying "
        f"methods {_METHODS} with {retries_per_method} retry each: {last_error}"
    ) from last_error
