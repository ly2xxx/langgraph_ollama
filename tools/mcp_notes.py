"""Optional MCP tool source: consume an md-mcp server as LangChain tools.

Two connection modes, in order of preference:

1. ``MD_MCP_URL`` (e.g. ``http://localhost:8000/mcp``) — connect to a
   long-lived md-mcp server over streamable-http. Fast (no container spawn
   per call) and observable: the app's instrumented httpx client sends the
   W3C ``traceparent`` header, so md-mcp's spans join the agent's trace —
   one distributed trace across both services. ``demo.ps1`` starts such a
   container wired to the OTel collector.
2. ``MD_MCP_FOLDER`` — spawn an md-mcp Docker container per session using
   stdio transport. Zero setup, but each MCP session pays a ``docker run``
   startup cost and the container has no collector access (no server-side
   spans).

The server's tools (``search_markdown``, ``list_files``, ...) are exposed as
LangChain tools the RAG agent can call. If neither variable is set or the
server is unreachable, ``load_md_mcp_tools`` returns ``[]`` and the app
behaves exactly as before.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import List

logger = logging.getLogger(__name__)

_FAILURE_RETRY_SECONDS = 60.0

# Module-level cache: Streamlit re-runs the whole script on every interaction,
# and tool discovery does a network round-trip. Successes are cached for the
# process lifetime; failures are retried at most once a minute so a later
# `docker start` of md-mcp is picked up without restarting the app.
_cached_tools: List | None = None
_last_failure_at: float = 0.0


def _openinference_span_context(callbacks):
    """OTel context parented to this tool call's OpenInference span, or None.

    OpenInference builds its span tree from LangChain callbacks WITHOUT
    attaching OTel runtime context (deliberately — see the comment in their
    _tracer.py). Consequence: outbound HTTP made inside a tool (our MCP calls)
    starts a fresh root trace, so md-mcp's server spans land in a separate
    trace from the agent run. LangChain hands the tool a child callback
    manager whose parent_run_id is the tool run's id; OpenInference exposes
    span lookup by run id — bridging the two lets us attach the right parent
    for exactly the duration of the MCP call.
    """
    try:
        run_id = getattr(callbacks, "parent_run_id", None)
        if run_id is None:
            return None
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry import trace as trace_api

        span = LangChainInstrumentor().get_span(run_id)
        if span is None:
            return None
        return trace_api.set_span_in_context(span)
    except Exception:
        return None


def _sync_wrap(async_tool):
    """MCP adapter tools are async-only; AgentExecutor here runs sync."""
    from langchain_core.tools import StructuredTool

    def _run(callbacks=None, **kwargs):
        # Attach the agent trace's span around the MCP round-trip so the
        # instrumented httpx client propagates its traceparent — this is what
        # stitches md-mcp's spans into the same distributed trace.
        token = None
        ctx = _openinference_span_context(callbacks)
        if ctx is not None:
            from opentelemetry import context as context_api

            token = context_api.attach(ctx)
        try:
            return asyncio.run(async_tool.ainvoke(kwargs))
        finally:
            if token is not None:
                from opentelemetry import context as context_api

                context_api.detach(token)

    return StructuredTool.from_function(
        func=_run,
        coroutine=async_tool.ainvoke,
        name=async_tool.name,
        description=async_tool.description,
        args_schema=async_tool.args_schema,
    )


def load_md_mcp_tools() -> List:
    """Return LangChain tools backed by the md-mcp server, or [] if unavailable."""
    global _cached_tools, _last_failure_at

    url = os.getenv("MD_MCP_URL")
    folder = os.getenv("MD_MCP_FOLDER")
    if not url and not folder:
        return []

    if _cached_tools is not None:
        return _cached_tools
    if time.monotonic() - _last_failure_at < _FAILURE_RETRY_SECONDS:
        return []

    if url:
        source = url
        server_cfg = {"url": url, "transport": "streamable_http"}
    else:
        source = folder
        server_cfg = {
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "-e",
                "MD_TRANSPORT=stdio",
                "-v",
                f"{folder}:/data",
                "ly2xxx/md-mcp:latest",
            ],
            "transport": "stdio",
        }

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({"md_notes": server_cfg})
        async_tools = asyncio.run(client.get_tools())
        _cached_tools = [_sync_wrap(t) for t in async_tools]
        logger.info(
            "md-mcp connected (%s) via %s: %s",
            server_cfg["transport"],
            source,
            [t.name for t in _cached_tools],
        )
        return _cached_tools
    except Exception as exc:
        _last_failure_at = time.monotonic()
        logger.warning("md-mcp unavailable at %s (%s) - continuing without it", source, exc)
        return []
