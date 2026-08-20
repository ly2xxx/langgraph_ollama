"""Top-level coordinator agent that delegates to Coding Engineer harnesses via A2A.

The coordinator is a compiled LangGraph graph.  It receives an instruction
(and an A2A endpoint URL), sends a ``tasks/send`` JSON-RPC request to the
Coding Engineer harness's A2A server, and returns the result together with
a delegation log that records what was sent and what came back.

Usage::

    from coordinator import build_coordinator

    graph = build_coordinator()
    result = graph.invoke({
        "instruction": "Write a Python function that returns the factorial of n",
        "a2a_endpoint": "http://localhost:8080",
    })
"""
from __future__ import annotations

import json
import time
import uuid
from typing import TypedDict

import httpx
from langgraph.graph import END, StateGraph


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class CoordinatorState(TypedDict, total=False):
    """State for the coordinator graph.

    Accepts several input shapes so the graph can be invoked with any of the
    common conventions (``instruction``, ``input``, ``task``, or ``messages``).
    """

    instruction: str
    a2a_endpoint: str
    messages: list
    input: str
    task: str
    result: str
    delegation_log: list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_instruction(state: CoordinatorState) -> str:
    """Pull the instruction out of whichever field the caller populated."""
    if state.get("instruction"):
        return state["instruction"]
    if state.get("input"):
        return state["input"]
    if state.get("task"):
        return state["task"]
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            content = getattr(msg, "content", "")
        if content:
            return content
    return ""


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


def delegate_node(state: CoordinatorState) -> dict:
    """Delegate the instruction to a Coding Engineer harness via A2A.

    Sends a ``tasks/send`` JSON-RPC request to the harness's A2A endpoint
    and records the response in ``delegation_log`` and ``result``.
    """
    instruction = _extract_instruction(state)
    endpoint = state.get("a2a_endpoint", "http://localhost:8080")

    task_id = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "id": task_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": instruction}],
            },
        },
        "id": 1,
    }

    # Retry briefly in case the server is still starting up.
    response = None
    for attempt in range(3):
        try:
            response = httpx.post(endpoint, json=payload, timeout=60.0)
            break
        except httpx.ConnectError:
            if attempt < 2:
                time.sleep(1)
            else:
                raise

    data = response.json()
    result = data.get("result", {})

    delegation_log = list(state.get("delegation_log") or [])
    delegation_log.append(
        {
            "task_id": task_id,
            "endpoint": endpoint,
            "instruction": instruction,
            "state": result.get("state"),
            "delegated": True,
        }
    )

    return {
        "result": json.dumps(result, default=str),
        "delegation_log": delegation_log,
    }


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_coordinator():
    """Build and compile the coordinator LangGraph."""
    graph = StateGraph(CoordinatorState)
    graph.add_node("delegate", delegate_node)
    graph.set_entry_point("delegate")
    graph.add_edge("delegate", END)
    return graph.compile()


# Pre-built instance for convenience imports.
coordinator = build_coordinator()