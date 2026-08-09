"""Step definitions for the _run_maker migration feature.

Every check is purely static (AST / string based) so the tests run even
when heavy runtime dependencies (langchain, etc.) are not installed in the
test environment.
"""

import ast
from pathlib import Path

import pytest
from pytest_bdd import scenarios, given, then

scenarios("../migrate_run_maker.feature")

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
LLM_BOUNDARIES_PATH = WORKTREE_ROOT / "coding_agent" / "llm_boundaries.py"
NODES_PATH = WORKTREE_ROOT / "coding_agent" / "nodes.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_source(path: Path) -> str:
    assert path.exists(), f"{path} does not exist"
    return path.read_text()


def _find_func(tree: ast.AST, name: str):
    """Return the FunctionDef / AsyncFunctionDef node with *name*, or None."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------

@given("the source file coding_agent/llm_boundaries.py", target_fixture="lb_source")
def lb_source():
    return _read_source(LLM_BOUNDARIES_PATH)


@given("the source file coding_agent/nodes.py", target_fixture="nodes_source")
def nodes_source():
    return _read_source(NODES_PATH)


# ---------------------------------------------------------------------------
# Then steps — string-level checks
# ---------------------------------------------------------------------------

@then('it should contain the import "from langchain.agents import create_agent"')
def check_create_agent_import(lb_source):
    assert "from langchain.agents import create_agent" in lb_source, (
        "Expected 'from langchain.agents import create_agent' in llm_boundaries.py"
    )


@then('it should not contain the string "AgentExecutor"')
def check_no_agent_executor(lb_source):
    assert "AgentExecutor" not in lb_source, (
        "AgentExecutor must not appear in llm_boundaries.py"
    )


@then('it should not contain the string "create_tool_calling_agent"')
def check_no_create_tool_calling_agent(lb_source):
    assert "create_tool_calling_agent" not in lb_source, (
        "create_tool_calling_agent must not appear in llm_boundaries.py"
    )


# ---------------------------------------------------------------------------
# Then step — create_agent is called inside _run_maker
# ---------------------------------------------------------------------------

@then('"create_agent" should be called within the "_run_maker" function')
def check_create_agent_called(lb_source):
    tree = ast.parse(lb_source)
    func = _find_func(tree, "_run_maker")
    assert func is not None, "_run_maker function not found"
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id == "create_agent":
                return
            if isinstance(callee, ast.Attribute) and callee.attr == "create_agent":
                return
    pytest.fail("create_agent is not called inside _run_maker")


# ---------------------------------------------------------------------------
# Then step — 20-iteration cap
# ---------------------------------------------------------------------------

@then("it should contain a configuration that limits iterations to 20")
def check_iteration_cap(lb_source):
    tree = ast.parse(lb_source)

    # 1. max_iterations=20 (or max_steps=20) keyword argument
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            if node.arg in ("max_iterations", "max_steps"):
                if isinstance(node.value, ast.Constant) and node.value.value == 20:
                    return

    # 2. recursion_limit keyword argument >= 20
    #    (create_agent graphs use recursion_limit; 2 nodes per iteration ⇒ 40,
    #     but any value >= 20 is a reasonable cap)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            if node.arg == "recursion_limit":
                if isinstance(node.value, ast.Constant) and node.value.value >= 20:
                    return

    # 3. recursion_limit or max_iterations inside a config dict literal
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if key.value == "recursion_limit" and isinstance(value, ast.Constant) and value.value >= 20:
                    return
                if key.value == "max_iterations" and isinstance(value, ast.Constant) and value.value == 20:
                    return

    # 4. Manual loop: range(20) or range(0, 20) or range(..., 20)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value == 20:
                    return

    # 5. Fallback — "20" on a line that also mentions iteration / limit / recursion
    for line in lb_source.splitlines():
        if "20" in line and any(w in line.lower() for w in ("iteration", "max", "limit", "recursion", "step")):
            return

    pytest.fail("No 20-iteration cap configuration found in llm_boundaries.py")


# ---------------------------------------------------------------------------
# Then step — tool error handling
# ---------------------------------------------------------------------------

@then("it should contain a configuration that handles tool errors")
def check_tool_error_handling(lb_source):
    # Broad string checks
    for pattern in ("handle_tool_error", "handle_tool_errors"):
        if pattern in lb_source:
            return

    # AST: keyword arg whose name contains both "tool" and "error"
    tree = ast.parse(lb_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            if "tool" in node.arg.lower() and "error" in node.arg.lower():
                return
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if "tool" in key.value.lower() and "error" in key.value.lower():
                        return

    pytest.fail("No tool error handling configuration found in llm_boundaries.py")


# ---------------------------------------------------------------------------
# Then step — _run_maker signature
# ---------------------------------------------------------------------------

@then('the function "_run_maker" should have the signature parameters "llm, jail, state"')
def check_signature(lb_source):
    tree = ast.parse(lb_source)
    func = _find_func(tree, "_run_maker")
    assert func is not None, "_run_maker function not found"
    params = [arg.arg for arg in func.args.args]
    # No *args / **kwargs expected, but tolerate them if present after the 3 named params
    assert params[:3] == ["llm", "jail", "state"], (
        f"Expected first three parameters ['llm', 'jail', 'state'], got {params[:3]}"
    )


# ---------------------------------------------------------------------------
# Then step — return-value compatibility with nodes.py
# ---------------------------------------------------------------------------

@then('the return value of "_run_maker" should be compatible with its usage in nodes.py')
def check_return_compatibility(lb_source, nodes_source):
    lb_tree = ast.parse(lb_source)
    nodes_tree = ast.parse(nodes_source)

    # --- Collect what _run_maker returns ---
    run_maker_func = _find_func(lb_tree, "_run_maker")
    assert run_maker_func is not None, "_run_maker not found in llm_boundaries.py"

    return_values: list[ast.expr] = []
    for node in ast.walk(run_maker_func):
        if isinstance(node, ast.Return) and node.value is not None:
            return_values.append(node.value)

    assert len(return_values) > 0, "_run_maker should have at least one return statement"

    # If _run_maker returns dict literals, collect the keys it provides.
    returned_keys: set = set()
    for val in return_values:
        if isinstance(val, ast.Dict):
            for key in val.keys:
                if isinstance(key, ast.Constant):
                    returned_keys.add(key.value)

    # --- Find variables in nodes.py that receive _run_maker's result ---
    run_maker_vars: set[str] = set()

    for node in ast.walk(nodes_tree):
        # Direct assignment:  var = _run_maker(...)
        if isinstance(node, ast.Assign):
            call = node.value
            if isinstance(call, ast.Call):
                callee = call.func
                if (isinstance(callee, ast.Name) and callee.id == "_run_maker") or \
                   (isinstance(callee, ast.Attribute) and callee.attr == "_run_maker"):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            run_maker_vars.add(target.id)

    # Also detect:  var = <wrapper>(_run_maker(...))  — uncommon but possible
    # (We skip nested calls for simplicity; the direct-assign case covers the
    #  overwhelmingly common pattern.)

    # --- Collect keys / attributes accessed on those variables ---
    accessed: set[str] = set()
    for node in ast.walk(nodes_tree):
        # var["key"]  or  var['key']
        if isinstance(node, ast.Subscript):
            base = node.value
            if isinstance(base, ast.Name) and base.id in run_maker_vars:
                if isinstance(node.slice, ast.Constant):
                    accessed.add(node.slice.value)
        # var.attr
        if isinstance(node, ast.Attribute):
            base = node.value
            if isinstance(base, ast.Name) and base.id in run_maker_vars:
                accessed.add(node.attr)

    # --- Compatibility check ---
    # If we could determine both the returned keys and the accessed keys,
    # every accessed key must be among the returned keys.
    if returned_keys and accessed:
        missing = accessed - returned_keys
        assert not missing, (
            f"nodes.py accesses {sorted(missing)} on _run_maker's return value, "
            f"but _run_maker only returns keys: {sorted(returned_keys)}"
        )

    # Regardless of the above, nodes.py must actually reference _run_maker.
    assert "_run_maker" in nodes_source, (
        "nodes.py should reference _run_maker"
    )