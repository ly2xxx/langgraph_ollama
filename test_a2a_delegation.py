"""End-to-end test: coordinator delegates a task to a Coding Engineer harness via A2A.

This script demonstrates the coordinator agent delegating a coding task to a
Coding Engineer harness through the A2A protocol and successfully retrieving
the result.

Run with::

    pytest test_a2a_delegation.py -v
    # or as a standalone script:
    python test_a2a_delegation.py
"""
from __future__ import annotations

import json
import socket
import threading
import time

import pytest


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def a2a_server_url():
    """Start the A2A server on a free port and return its URL."""
    import uvicorn
    from a2a_server import app

    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(2)
    url = f"http://127.0.0.1:{port}"
    yield url


def test_coordinator_delegates_task_to_a2a_harness(a2a_server_url):
    """Coordinator delegates a task to the Coding Engineer harness via A2A."""
    from coordinator import build_coordinator

    graph = build_coordinator()
    result = graph.invoke(
        {
            "instruction": "Write a Python function that returns the factorial of n",
            "a2a_endpoint": a2a_server_url,
        }
    )

    assert result is not None
    assert "result" in result
    result_str = json.dumps(result, default=str)
    assert "completed" in result_str.lower()
    assert "delegation_log" in result
    assert result["delegation_log"][0]["delegated"] is True
    print(f"Delegation successful — coordinator delegated task to harness via A2A")
    print(f"Result: {result}")


def test_a2a_delegation_retrieves_result_from_harness(a2a_server_url):
    """Coordinator successfully retrieves the result from the harness."""
    from coordinator import build_coordinator

    graph = build_coordinator()
    result = graph.invoke(
        {
            "instruction": "Implement a function that adds two numbers",
            "a2a_endpoint": a2a_server_url,
        }
    )

    assert result is not None
    result_str = json.dumps(result, default=str)
    assert "result" in result_str
    assert "completed" in result_str.lower()
    print(f"Result retrieved from harness: {result}")


if __name__ == "__main__":
    # Run as a standalone script
    import uvicorn
    from a2a_server import app
    from coordinator import build_coordinator

    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(2)

    url = f"http://127.0.0.1:{port}"
    graph = build_coordinator()
    result = graph.invoke(
        {
            "instruction": "Write a Python function that returns the factorial of n",
            "a2a_endpoint": url,
        }
    )

    print(f"Coordinator delegated task to Coding Engineer harness via A2A at {url}")
    print(f"Task delegation completed successfully")
    print(f"Result retrieved from harness: {json.dumps(result, default=str)}")
    print("End-to-end A2A delegation test passed!")