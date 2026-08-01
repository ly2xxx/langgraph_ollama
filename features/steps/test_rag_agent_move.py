"""Step definitions for the rag_agent move feature.

These tests verify that rag_research_chatbot.py has been moved into a
rag_agent/ subfolder and that all imports have been updated accordingly.
"""

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import scenarios, given, then

scenarios("../rag_agent_move.feature")

# ---------------------------------------------------------------------------
# Worktree root discovery
# ---------------------------------------------------------------------------
# This file lives at <worktree-root>/features/steps/test_rag_agent_move.py
# so the worktree root is three parents up.
WORKTREE_ROOT = Path(__file__).resolve().parent.parent.parent

# Ensure the worktree root is importable so `import rag_agent...` works.
_root_str = str(WORKTREE_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------

@given("the worktree has been refactored")
def the_worktree_has_been_refactored():
    """Placeholder step — the refactoring is expected to already be complete."""
    pass


# ---------------------------------------------------------------------------
# Then steps — filesystem checks
# ---------------------------------------------------------------------------

@then('a directory named "rag_agent" exists in the worktree root')
def directory_exists():
    rag_agent_dir = WORKTREE_ROOT / "rag_agent"
    assert rag_agent_dir.is_dir(), (
        f"Directory 'rag_agent' does not exist in {WORKTREE_ROOT}"
    )


@then('a file named "rag_agent/rag_research_chatbot.py" exists in the worktree')
def moved_file_exists():
    filepath = WORKTREE_ROOT / "rag_agent" / "rag_research_chatbot.py"
    assert filepath.is_file(), (
        f"File 'rag_agent/rag_research_chatbot.py' does not exist"
    )


@then('a file named "rag_research_chatbot.py" does not exist in the worktree root')
def original_file_removed():
    filepath = WORKTREE_ROOT / "rag_research_chatbot.py"
    assert not filepath.is_file(), (
        f"File 'rag_research_chatbot.py' still exists in worktree root {WORKTREE_ROOT}"
    )


@then('a file named "rag_agent/__init__.py" exists in the worktree')
def init_file_exists():
    filepath = WORKTREE_ROOT / "rag_agent" / "__init__.py"
    assert filepath.is_file(), (
        f"File 'rag_agent/__init__.py' does not exist"
    )


# ---------------------------------------------------------------------------
# Then steps — class preservation
# ---------------------------------------------------------------------------

@then('the file "rag_agent/rag_research_chatbot.py" defines at least one class')
def file_defines_class():
    filepath = WORKTREE_ROOT / "rag_agent" / "rag_research_chatbot.py"
    source = filepath.read_text()
    tree = ast.parse(source)
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert len(classes) > 0, (
        f"No class definitions found in {filepath}"
    )


@then('the class is importable from "rag_agent.rag_research_chatbot"')
def class_is_importable():
    # Force a fresh import to avoid stale module cache.
    for mod_name in list(sys.modules):
        if mod_name.startswith("rag_agent"):
            del sys.modules[mod_name]
    mod = importlib.import_module("rag_agent.rag_research_chatbot")
    classes = [
        obj for _name, obj in inspect.getmembers(mod, inspect.isclass)
        if obj.__module__ == "rag_agent.rag_research_chatbot"
    ]
    assert len(classes) > 0, (
        "No classes defined in rag_agent.rag_research_chatbot could be imported. "
        f"Members: {[name for name, _ in inspect.getmembers(mod)]}"
    )


# ---------------------------------------------------------------------------
# Then steps — import hygiene
# ---------------------------------------------------------------------------

@then('no Python file outside "rag_agent" contains an import of "rag_research_chatbot" without the "rag_agent" prefix')
def no_bare_imports():
    bad_imports = []
    for py_file in WORKTREE_ROOT.rglob("*.py"):
        rel = py_file.relative_to(WORKTREE_ROOT)
        parts = rel.parts

        # Skip files inside rag_agent/ — relative imports are allowed there.
        if len(parts) > 1 and parts[0] == "rag_agent":
            continue

        # Skip our own test / feature files.
        if "features" in parts:
            continue

        try:
            source = py_file.read_text()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # e.g.  import rag_research_chatbot
                    if alias.name == "rag_research_chatbot":
                        bad_imports.append(
                            f"{rel}: `import rag_research_chatbot`"
                        )
            elif isinstance(node, ast.ImportFrom):
                # e.g.  from rag_research_chatbot import Foo
                # (level == 0 means absolute import — relative imports are
                #  already excluded because we skip files inside rag_agent/)
                if node.module == "rag_research_chatbot" and node.level == 0:
                    bad_imports.append(
                        f"{rel}: `from rag_research_chatbot import ...`"
                    )

    assert not bad_imports, (
        "Found bare imports of rag_research_chatbot without the rag_agent prefix:\n"
        + "\n".join(bad_imports)
    )


# ---------------------------------------------------------------------------
# Then steps — runtime import checks
# ---------------------------------------------------------------------------

@then('importing "rag_agent.rag_research_chatbot" completes without ImportError or ModuleNotFoundError')
def module_imports_without_error():
    # Force a fresh import.
    for mod_name in list(sys.modules):
        if mod_name.startswith("rag_agent"):
            del sys.modules[mod_name]
    try:
        importlib.import_module("rag_agent.rag_research_chatbot")
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"Importing rag_agent.rag_research_chatbot failed: {exc}")


@then('running "python -m pytest --collect-only -q" in the worktree root does not produce ImportError or ModuleNotFoundError')
def test_command_no_import_errors():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(WORKTREE_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    # Show the tail of the output for debugging if it fails.
    tail = output[-2000:] if len(output) > 2000 else output
    assert "ImportError" not in output, (
        f"ImportError found in pytest --collect-only output:\n{tail}"
    )
    assert "ModuleNotFoundError" not in output, (
        f"ModuleNotFoundError found in pytest --collect-only output:\n{tail}"
    )