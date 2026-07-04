"""Optional MCP tool source: consume an md-mcp server as LangChain tools.

If ``MD_MCP_URL`` is set (e.g. ``http://localhost:8000/mcp`` for a local
md-mcp Docker container in streamable-http mode), this module connects via
``langchain-mcp-adapters`` and exposes the server's tools
(``search_markdown``, ``list_files``, ...) as LangChain tools the RAG agent
can call. The agent then gets a personal-notes knowledge base with zero local
indexing — retrieval stays in md-mcp, where it is chunked, cached and (if the
collector is up) OTel-traced.

If ``MD_MCP_URL`` is unset or the server is unreachable, ``load_md_mcp_tools``
returns ``[]`` and the app behaves exactly as before.
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


def _sync_wrap(async_tool):
    """MCP adapter tools are async-only; AgentExecutor here runs sync."""
    from langchain_core.tools import StructuredTool

    def _run(**kwargs):
        return asyncio.run(async_tool.ainvoke(kwargs))

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
    if not url:
        return []

    if _cached_tools is not None:
        return _cached_tools
    if time.monotonic() - _last_failure_at < _FAILURE_RETRY_SECONDS:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(
            {"md_notes": {"url": url, "transport": "streamable_http"}}
        )
        async_tools = asyncio.run(client.get_tools())
        _cached_tools = [_sync_wrap(t) for t in async_tools]
        logger.info(
            "md-mcp connected at %s: %s", url, [t.name for t in _cached_tools]
        )
        return _cached_tools
    except Exception as exc:
        _last_failure_at = time.monotonic()
        logger.warning("md-mcp unavailable at %s (%s) - continuing without it", url, exc)
        return []
