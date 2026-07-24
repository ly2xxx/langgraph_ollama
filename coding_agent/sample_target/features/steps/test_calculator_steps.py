"""Step definitions for features/calculator.feature.

Imports the target implementation under test (calculator.add) rather than
reimplementing the arithmetic here — a passing step suite is real evidence
the kata is solved, not a rubber stamp. This file, like calculator.py, is
what the Coding Engineer's maker is allowed to edit; features/calculator.feature
itself is frozen once the loop starts (see CODING_ENGINEER.md §2, §3.3).
"""

import sys
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from calculator import add

scenarios("../calculator.feature")


@pytest.fixture
def context():
    return {}


@given(parsers.re(r'the string "(?P<value>.*)"'))
def given_string(context, value):
    # Feature files can't embed a real newline inside a quoted step
    # argument, so "\n" is written literally and unescaped here.
    context["input"] = value.replace("\\n", "\n")


@when("I add the numbers")
def when_add(context):
    try:
        context["result"] = add(context["input"])
    except Exception as exc:  # noqa: BLE001 — captured for the error scenario
        context["error"] = exc


@then(parsers.parse("the result should be {expected:d}"))
def then_result(context, expected):
    assert "error" not in context, f"add() raised unexpectedly: {context.get('error')!r}"
    assert context["result"] == expected


@then(parsers.parse('it should raise an error containing "{substring}"'))
def then_error(context, substring):
    assert "error" in context, "add() was expected to raise but did not"
    assert substring in str(context["error"])
