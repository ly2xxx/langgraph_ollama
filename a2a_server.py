"""A2A-compatible server for the Coding Engineer harness.

Exposes an Agent Card at the standard A2A discovery endpoint
``/.well-known/agent.json`` and a JSON-RPC endpoint that accepts
``tasks/send`` requests following the A2A (Agent-to-Agent) protocol.

The server wraps the Coding Engineer harness (``coding_engineer`` / ``coding_agent``).
In production the ``_process_task`` function would invoke the harness graph
against a target worktree; for lightweight deployments and tests it returns a
completed task with the message echoed back as an artifact.
"""
from __future__ import annotations

import uuid

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

# ---------------------------------------------------------------------------
# Agent Card — advertised at /.well-known/agent.json
# ---------------------------------------------------------------------------

AGENT_CARD: dict = {
    "name": "Coding Engineer",
    "description": (
        "A coding engineer agent that implements code changes against "
        "acceptance criteria using a non-stop coding loop with BDD gates, "
        "differential linting, and adversarial review."
    ),
    "url": "http://localhost:8080",
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionRadius": False,
    },
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": [
        {
            "id": "implement-code",
            "name": "Implement Code",
            "description": "Implement code changes against acceptance criteria.",
        }
    ],
}


# ---------------------------------------------------------------------------
# Task processing
# ---------------------------------------------------------------------------


def _process_task(task_id: str, message_text: str) -> dict:
    """Process a single task and return the A2A task object.

    In a full deployment this would invoke ``coding_engineer.build_graph()``
    against a target worktree.  For the A2A protocol layer (and for tests
    that only exercise the protocol) we return a completed task with the
    instruction echoed as an artifact.
    """
    return {
        "id": task_id,
        "state": "completed",
        "artifacts": [
            {
                "name": "result",
                "parts": [{"type": "text", "text": f"Task completed: {message_text}"}],
            }
        ],
    }


# ---------------------------------------------------------------------------
# ASGI handlers
# ---------------------------------------------------------------------------


async def agent_card_endpoint(request):
    """Serve the Agent Card at the well-known discovery endpoint."""
    return JSONResponse(AGENT_CARD)


async def jsonrpc_endpoint(request):
    """Handle JSON-RPC 2.0 requests (``tasks/send`` and friends)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
            status_code=200,
        )

    method = body.get("method", "")
    rpc_id = body.get("id")

    if method == "tasks/send":
        params = body.get("params", {})
        task_id = params.get("id") or str(uuid.uuid4())
        message = params.get("message", {})
        parts = message.get("parts", [])
        message_text = " ".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
        )
        result = _process_task(task_id, message_text)
        return JSONResponse({"jsonrpc": "2.0", "result": result, "id": rpc_id})

    # Unknown method
    return JSONResponse(
        {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": rpc_id},
        status_code=200,
    )


# ---------------------------------------------------------------------------
# App assembly
# ---------------------------------------------------------------------------

routes = [
    Route("/.well-known/agent.json", agent_card_endpoint),
    Route("/", jsonrpc_endpoint, methods=["POST"]),
    Route("/tasks/send", jsonrpc_endpoint, methods=["POST"]),
    Route("/jsonrpc", jsonrpc_endpoint, methods=["POST"]),
    Route("/a2a", jsonrpc_endpoint, methods=["POST"]),
    Route("/rpc", jsonrpc_endpoint, methods=["POST"]),
]

app = Starlette(routes=routes)


def create_app() -> Starlette:
    """Factory that returns the A2A server ASGI application."""
    return app