"""Regression tests for self_check failure attribution.

Taken from run 20260917T151556-c43a71ed, which escalated with
two_plans_exhausted after diagnose told the agent three times to fix ruff --
while ruff had exited 0 and the real error was a pytest collection ImportError
saying the function under test did not exist. The detail handed to diagnose was
the literal string "ruff findings: " with nothing after it, and the signature was
a constant, so two such attempts tripped the "same signature twice" rule and
burned the plan.
"""
import pytest

from coding_agent.nodes import _signature_and_detail

# ruff clean, pytest exited 2 during collection -- `failures` is empty because a
# collection error is not a test failure.
COLLECTION_ERROR = {
    "test_report": {
        "ruff": {"returncode": 0, "stdout": "", "stderr": ""},
        "ruff_codes": [],
        "pytest": {
            "returncode": 2,
            "stdout": (
                "=================================== ERRORS ===================="
                "\nERROR collecting tests/test_smoke.py\n"
                "tests\\test_smoke.py:9: in <module>\n    from src.retry import retry\n"
                "E   ImportError: cannot import name 'retry' from 'src.retry'\n"
            ),
            "stderr": "",
            "summary": {"total": 0, "collected": 0},
            "failures": [],
        },
        "passed": False,
    }
}


def _detail(state):
    return _signature_and_detail(state, "self_check")[1]


def _sig(state):
    return _signature_and_detail(state, "self_check")[0]


def test_collection_error_is_not_reported_as_a_ruff_failure():
    detail = _detail(COLLECTION_ERROR)
    assert "ruff findings" not in detail
    assert "NOT a lint failure" in detail


def test_collection_error_detail_carries_the_real_error():
    detail = _detail(COLLECTION_ERROR)
    assert "ImportError" in detail
    assert "cannot import name 'retry'" in detail


def test_collection_error_signature_varies_with_the_error():
    """A constant signature made every collection error look like no-progress."""
    import copy

    other = copy.deepcopy(COLLECTION_ERROR)
    other["test_report"]["pytest"]["stdout"] = (
        "ERROR collecting tests/test_smoke.py\nE   SyntaxError: invalid syntax\n"
    )
    assert _sig(COLLECTION_ERROR) != _sig(other)


def test_a_real_ruff_failure_is_still_reported_as_ruff():
    state = {
        "test_report": {
            "ruff": {"returncode": 1, "stdout": "src/retry.py:3:1 F401 unused import"},
            "ruff_codes": ["F401"],
            "pytest": {"returncode": 0, "failures": [], "summary": {"collected": 1}},
            "passed": False,
        }
    }
    assert "ruff findings: F401" in _detail(state)


def test_structured_pytest_failures_still_take_priority():
    state = {
        "test_report": {
            "ruff": {"returncode": 0},
            "ruff_codes": [],
            "pytest": {
                "returncode": 1,
                "summary": {"collected": 4},
                "failures": [
                    {
                        "nodeid": "tests/test_x.py::test_y",
                        "message": "AssertionError: 1 != 2",
                        "error_class": "AssertionError",
                        "top_frame_func": "test_y",
                    }
                ],
            },
            "passed": False,
        }
    }
    detail = _detail(state)
    assert "tests/test_x.py::test_y" in detail
    assert "AssertionError" in detail


@pytest.mark.parametrize("rc", [0, 5])
def test_unidentifiable_failure_does_not_blame_a_passing_tool(rc):
    state = {
        "test_report": {
            "ruff": {"returncode": 0},
            "ruff_codes": [],
            "pytest": {"returncode": rc, "failures": [], "summary": {"collected": 0}},
            "passed": False,
        }
    }
    detail = _detail(state)
    if rc == 0:
        assert "neither ruff nor pytest" in detail
    else:
        assert "NOT a lint failure" in detail
