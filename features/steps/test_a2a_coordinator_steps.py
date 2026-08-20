"""
Step definitions for A2A coordinator integration feature.
Tests that the A2A protocol is properly integrated with the Coding Engineer harness
and that a LangGraph coordinator can delegate tasks via A2A.
"""
from pytest_bdd import scenarios, given, when, then, parsers
import pytest
import json
import importlib
import subprocess
import sys
import os
import time
import threading
import socket
import glob

scenarios("../a2a_coordinator.feature")


# ─── Helpers ──────────────────────────────────────────────────────────────

def _try_import(*module_paths):
    """Try to import from one of several possible module paths."""
    for path in module_paths:
        try:
            return importlib.import_module(path)
        except (ImportError, ModuleNotFoundError):
            continue
    return None


def _try_attr(module, *attr_names):
    """Try to get one of several attributes from a module."""
    for name in attr_names:
        if hasattr(module, name):
            return getattr(module, name)
    return None


def _find_free_port():
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_test_client(app):
    """Create a test client for the given app, trying different frameworks."""
    # Try FastAPI / Starlette
    try:
        from fastapi.testclient import TestClient
        return TestClient(app)
    except (ImportError, TypeError, Exception):
        pass
    try:
        from starlette.testclient import TestClient
        return TestClient(app)
    except (ImportError, TypeError, Exception):
        pass
    # Try Flask
    try:
        app.config["TESTING"] = True
        return app.test_client()
    except Exception:
        pass
    raise AssertionError(
        "Could not create a test client for the A2A server. "
        "Ensure the server uses FastAPI, Starlette, or Flask."
    )


# ─── Pytest fixtures (shared across scenarios) ─────────────────────────────

@pytest.fixture
def coordinator_graph(coordinator_module):
    """Build or retrieve the coordinator graph from the imported module."""
    graph = _try_attr(
        coordinator_module,
        "coordinator",
        "graph",
        "coordinator_graph",
        "app",
        "build_coordinator",
        "get_coordinator",
        "create_coordinator",
    )
    assert graph is not None, (
        f"Coordinator module {coordinator_module.__name__} has no "
        "coordinator/graph/coordinator_graph/app/build_coordinator/"
        "get_coordinator/create_coordinator attribute"
    )
    # If it's a factory function, call it
    if callable(graph) and not hasattr(graph, "invoke"):
        graph = graph()
    return graph


@pytest.fixture
def a2a_server_url(a2a_app):
    """Start the A2A server on a real port and return the URL.

    Used for integration tests where the coordinator makes real HTTP calls.
    """
    port = _find_free_port()
    try:
        import uvicorn

        config = uvicorn.Config(
            a2a_app, host="127.0.0.1", port=port, log_level="error"
        )
        server = uvicorn.Server(config)

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        time.sleep(2)  # Wait for server to start

        url = f"http://127.0.0.1:{port}"
        yield url
        # Server runs in a daemon thread; cleaned up on process exit
    except ImportError:
        pytest.skip(
            "uvicorn not installed; cannot start A2A server for integration test"
        )


# ─── Background steps ──────────────────────────────────────────────────────

@given("a Coding Engineer harness is available", target_fixture="harness_module")
def harness_available():
    """Verify that a Coding Engineer harness module can be imported."""
    module = _try_import(
        "coding_engineer",
        "coding_engineer.harness",
        "harness",
        "agent",
        "graph",
        "coding_engineer.graph",
    )
    assert module is not None, (
        "Could not import any Coding Engineer harness module. "
        "Tried: coding_engineer, coding_engineer.harness, harness, "
        "agent, graph, coding_engineer.graph"
    )
    return module


@given(
    "an A2A server is created for the Coding Engineer harness",
    target_fixture="a2a_app",
)
def a2a_server_created(harness_module):
    """Import and create the A2A server application."""
    server_module = _try_import(
        "a2a_server",
        "a2a.server",
        "coding_engineer.a2a_server",
        "server",
        "a2a",
    )
    assert server_module is not None, (
        "Could not import A2A server module. "
        "Tried: a2a_server, a2a.server, coding_engineer.a2a_server, server, a2a"
    )

    app = _try_attr(
        server_module,
        "app",
        "create_app",
        "build_app",
        "create_server",
        "application",
    )
    assert app is not None, (
        f"A2A server module {server_module.__name__} has no "
        "app/create_app/build_app/create_server/application attribute"
    )

    # If it's a factory function, call it
    if callable(app) and not hasattr(app, "get") and not hasattr(app, "test_client"):
        app = app()

    return app


# ─── Scenario 1: Agent Card at well-known endpoint ─────────────────────────

@when(
    'a GET request is made to "/.well-known/agent.json"',
    target_fixture="http_response",
)
def get_agent_card(a2a_app):
    client = _get_test_client(a2a_app)
    response = client.get("/.well-known/agent.json")
    return response


@then("the response status should be 200")
def check_response_status(http_response):
    assert http_response.status_code == 200, (
        f"Expected status 200, got {http_response.status_code}. "
        f"Body: {http_response.text[:500]}"
    )


@then("the response body should be valid JSON", target_fixture="agent_card")
def check_valid_json(http_response):
    try:
        data = http_response.json()
    except Exception as e:
        raise AssertionError(f"Response body is not valid JSON: {e}")
    assert isinstance(data, dict), (
        f"Agent card should be a JSON object, got {type(data).__name__}"
    )
    return data


@then(parsers.parse('the agent card "{field}" field should be a non-empty string'))
def check_string_field(agent_card, field):
    assert field in agent_card, (
        f"Agent card missing required field: '{field}'. "
        f"Available fields: {list(agent_card.keys())}"
    )
    value = agent_card[field]
    assert isinstance(value, str), (
        f"Agent card field '{field}' should be a string, "
        f"got {type(value).__name__}: {value}"
    )
    assert len(value) > 0, f"Agent card field '{field}' should be non-empty"


@then(parsers.parse('the agent card "{field}" field should be present'))
def check_field_present(agent_card, field):
    assert field in agent_card, (
        f"Agent card missing required field: '{field}'. "
        f"Available fields: {list(agent_card.keys())}"
    )


# ─── Scenario 2: Task processing via JSON-RPC ──────────────────────────────

@given(
    parsers.parse(
        'a JSON-RPC request with method "{method}" and message "{message}"'
    ),
    target_fixture="jsonrpc_request",
)
def make_jsonrpc_request(method, message):
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": {
            "id": "test-task-001",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
        },
        "id": 1,
    }


@when(
    "the request is sent to the A2A server",
    target_fixture="http_response",
)
def send_jsonrpc_request(a2a_app, jsonrpc_request):
    client = _get_test_client(a2a_app)

    # Try common A2A JSON-RPC endpoints
    endpoints = ["/", "/tasks/send", "/jsonrpc", "/a2a", "/rpc"]
    for endpoint in endpoints:
        try:
            response = client.post(endpoint, json=jsonrpc_request)
            if response.status_code != 404:
                return response
        except Exception:
            continue

    raise AssertionError(
        f"Could not find a working A2A JSON-RPC endpoint. Tried: {endpoints}"
    )


@then("the response should contain a result key")
def check_result_key(http_response):
    data = http_response.json()
    assert "result" in data, (
        f"Response should contain 'result' key. "
        f"Got keys: {list(data.keys())}. Body: {json.dumps(data)[:500]}"
    )


@then(parsers.parse('the result should contain a task "{field}"'))
def check_task_field(http_response, field):
    data = http_response.json()
    result = data.get("result", data)
    assert isinstance(result, dict), (
        f"Result should be a dict to check for '{field}'. "
        f"Got: {type(result).__name__}"
    )
    assert field in result, (
        f"Result should contain task '{field}'. "
        f"Got keys: {list(result.keys())}. "
        f"Result: {json.dumps(result, default=str)[:500]}"
    )


# ─── Scenario 3: Coordinator is a compiled LangGraph ───────────────────────

@given("the coordinator module is imported", target_fixture="coordinator_module")
def import_coordinator():
    module = _try_import(
        "coordinator",
        "coordinator.agent",
        "coordinator.graph",
        "coordinator_agent",
        "a2a_coordinator",
    )
    assert module is not None, (
        "Could not import coordinator module. "
        "Tried: coordinator, coordinator.agent, coordinator.graph, "
        "coordinator_agent, a2a_coordinator"
    )
    return module


@then("the coordinator graph should be a compiled LangGraph instance")
def check_langgraph(coordinator_graph):
    assert hasattr(coordinator_graph, "invoke"), (
        f"Coordinator graph should have an 'invoke' method. "
        f"Got type: {type(coordinator_graph).__name__}"
    )
    type_name = type(coordinator_graph).__name__
    module_name = type(coordinator_graph).__module__
    assert (
        "langgraph" in module_name.lower()
        or "compiled" in type_name.lower()
        or "graph" in type_name.lower()
    ), (
        f"Coordinator graph should be a LangGraph compiled graph. "
        f"Got type: {type_name} from module: {module_name}"
    )


@then(parsers.parse('the coordinator graph should have an "{method}" method'))
def check_graph_method(coordinator_graph, method):
    assert hasattr(coordinator_graph, method), (
        f"Coordinator graph should have '{method}' method. "
        f"Got type: {type(coordinator_graph).__name__}"
    )


# ─── Scenario 4: Coordinator delegates via A2A ─────────────────────────────

@given(
    "the coordinator is configured with the A2A endpoint URL",
    target_fixture="coordinator_configured",
)
def configure_coordinator(coordinator_graph, a2a_server_url):
    """Configure the coordinator with the A2A server endpoint URL.

    Tries multiple configuration approaches since the implementation
    may use any of: set_endpoint, configure, attribute assignment,
    or passing the URL at invocation time.
    """
    # Approach 1: set_endpoint method
    if hasattr(coordinator_graph, "set_endpoint"):
        try:
            coordinator_graph.set_endpoint(a2a_server_url)
        except Exception:
            pass
    # Approach 2: configure method
    elif hasattr(coordinator_graph, "configure"):
        try:
            coordinator_graph.configure(a2a_endpoint=a2a_server_url)
        except TypeError:
            try:
                coordinator_graph.configure(a2a_server_url)
            except TypeError:
                pass
    # Approach 3: Set as attribute
    elif hasattr(coordinator_graph, "a2a_endpoint"):
        coordinator_graph.a2a_endpoint = a2a_server_url
    # Approach 4: The endpoint will be passed in the invoke input

    return {"graph": coordinator_graph, "endpoint": a2a_server_url}


@given(
    parsers.parse('a delegation instruction "{instruction}"'),
    target_fixture="delegation_instruction",
)
def set_delegation_instruction(instruction):
    return instruction


@when(
    "the coordinator processes the instruction",
    target_fixture="coordinator_result",
)
def process_instruction(coordinator_configured, delegation_instruction):
    graph = coordinator_configured["graph"]
    endpoint = coordinator_configured["endpoint"]

    # Try different input formats the coordinator might accept
    input_variants = [
        {
            "instruction": delegation_instruction,
            "a2a_endpoint": endpoint,
        },
        {
            "messages": [
                {"role": "user", "content": delegation_instruction}
            ],
            "a2a_endpoint": endpoint,
        },
        {"input": delegation_instruction, "a2a_endpoint": endpoint},
        {"task": delegation_instruction, "a2a_endpoint": endpoint},
        {
            "messages": [
                {"role": "user", "content": delegation_instruction}
            ]
        },
        {"instruction": delegation_instruction},
        {"input": delegation_instruction},
        {"task": delegation_instruction},
    ]

    result = None
    errors = []
    for inp in input_variants:
        try:
            result = graph.invoke(inp)
            break
        except Exception as e:
            errors.append(
                f"input={type(inp).__name__}: {type(e).__name__}: {e}"
            )

    if result is None:
        raise AssertionError(
            "Could not invoke coordinator with any input format.\n"
            "Errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return result


@then("the coordinator should return a non-empty result")
def check_non_empty_result(coordinator_result):
    assert coordinator_result is not None, "Coordinator returned None"
    if isinstance(coordinator_result, dict):
        assert len(coordinator_result) > 0, "Coordinator returned empty dict"
    elif isinstance(coordinator_result, str):
        assert len(coordinator_result) > 0, "Coordinator returned empty string"
    elif isinstance(coordinator_result, list):
        assert len(coordinator_result) > 0, "Coordinator returned empty list"


@then("the result should contain evidence of task delegation to the harness")
def check_delegation_evidence(coordinator_result):
    # Convert result to searchable string
    if isinstance(coordinator_result, str):
        result_str = coordinator_result
    else:
        result_str = json.dumps(coordinator_result, default=str)

    result_lower = result_str.lower()

    # Look for indicators of delegation / A2A communication
    delegation_indicators = [
        "delegat",
        "task",
        "a2a",
        "harness",
        "agent",
        "result",
        "complet",
        "response",
        "output",
        "send",
        "coordinator",
    ]
    found = [ind for ind in delegation_indicators if ind in result_lower]

    assert len(found) >= 2, (
        f"Result should contain evidence of task delegation to the harness. "
        f"Found indicators: {found}. "
        f"Result (truncated): {result_str[:500]}"
    )


# ─── Scenario 5: End-to-end test script exists and passes ──────────────────

@given(
    "a test or script file exists for coordinator-to-harness delegation",
    target_fixture="test_script_path",
)
def find_test_script():
    """Search for a test or script file demonstrating coordinator delegation."""
    patterns = [
        "test_*a2a*",
        "test_*coordinator*",
        "test_*delegat*",
        "demo_*a2a*",
        "demo_*coordinator*",
        "example*a2a*",
        "example*coordinator*",
        "run_*a2a*",
        "run_*coordinator*",
        "*a2a*demo*",
        "*coordinator*demo*",
        "*a2a*example*",
        "*coordinator*example*",
        "*a2a*integration*",
        "*coordinator*integration*",
    ]

    search_dirs = [
        ".",
        "tests",
        "test",
        "examples",
        "scripts",
        "demo",
        "demos",
        "integration_tests",
    ]

    found_files = []
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for pattern in patterns:
            found_files.extend(glob.glob(os.path.join(d, pattern + ".py")))
            found_files.extend(glob.glob(os.path.join(d, pattern + ".sh")))
            # Recursive search
            found_files.extend(
                glob.glob(
                    os.path.join(d, "**", pattern + ".py"), recursive=True
                )
            )
            found_files.extend(
                glob.glob(
                    os.path.join(d, "**", pattern + ".sh"), recursive=True
                )
            )

    # Deduplicate
    found_files = list(set(found_files))

    # Exclude this test file and feature files
    this_file = os.path.abspath(__file__)
    found_files = [
        f
        for f in found_files
        if os.path.abspath(f) != this_file and not f.endswith(".feature")
    ]

    assert len(found_files) > 0, (
        "No test or script file found for coordinator-to-harness delegation. "
        f"Searched patterns: {patterns} in dirs: {search_dirs}"
    )

    return found_files[0]


@when("the test or script is executed", target_fixture="script_result")
def execute_test_script(test_script_path):
    """Execute the test or script file."""
    if test_script_path.endswith(".py"):
        # Try running as a pytest test first, then as a plain script
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    test_script_path,
                    "-v",
                    "--tb=short",
                    "-x",
                ],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=os.getcwd(),
            )
            if result.returncode != 0:
                # Fall back to running as a plain script
                result = subprocess.run(
                    [sys.executable, test_script_path],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    cwd=os.getcwd(),
                )
        except subprocess.TimeoutExpired:
            raise AssertionError(
                f"Test script {test_script_path} timed out after 180 seconds"
            )
    elif test_script_path.endswith(".sh"):
        try:
            result = subprocess.run(
                ["bash", test_script_path],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=os.getcwd(),
            )
        except subprocess.TimeoutExpired:
            raise AssertionError(
                f"Test script {test_script_path} timed out after 180 seconds"
            )
    else:
        raise AssertionError(f"Unknown script type: {test_script_path}")

    return result


@then("the execution should complete without errors")
def check_no_errors(script_result):
    assert script_result.returncode == 0, (
        f"Script execution failed with return code {script_result.returncode}.\n"
        f"stdout:\n{script_result.stdout[:2000]}\n"
        f"stderr:\n{script_result.stderr[:2000]}"
    )


@then("the output should contain evidence of successful task delegation")
def check_delegation_output(script_result):
    output = (script_result.stdout + script_result.stderr).lower()
    indicators = ["delegat", "task", "a2a", "coordinator", "harness", "send"]
    found = [ind for ind in indicators if ind in output]
    assert len(found) >= 2, (
        f"Output should contain evidence of task delegation. "
        f"Found: {found}. "
        f"Output (truncated): {output[:500]}"
    )


@then("the output should contain evidence of result retrieval from the harness")
def check_retrieval_output(script_result):
    output = (script_result.stdout + script_result.stderr).lower()
    indicators = [
        "result",
        "complet",
        "output",
        "response",
        "success",
        "pass",
        "retriev",
    ]
    found = [ind for ind in indicators if ind in output]
    assert len(found) >= 1, (
        f"Output should contain evidence of result retrieval. "
        f"Found: {found}. "
        f"Output (truncated): {output[:500]}"
    )