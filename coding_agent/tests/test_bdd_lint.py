"""Both cases are taken verbatim from run 20260916T174956, which escalated with
two_plans_exhausted without ever editing the source file."""
from coding_agent.bdd_lint import lint_bdd

UNSATISFIABLE = '''Feature: Collapse whitespace
  Scenario: Collapses tabs and newlines
    Given the input string is "a\\t\\nb"
    When collapse_whitespace is called
    Then the result should be "a b"
'''
EMPTY_VALUE = '''Feature: Collapse whitespace
  Scenario: Empty string returns empty string
    Given the input string is ""
    When collapse_whitespace is called
    Then the result should be ""
'''
PARSE_STEPS = '''from pytest_bdd import given, parsers
@given(parsers.parse('the input string is "{input}"'))
def set_input(context, input): context['input'] = input
'''
RE_STEPS = '''from pytest_bdd import given, parsers
@given(parsers.re(r'the input string is "(?P<input>[^"]*)"'))
def set_input(context, input): context['input'] = input
'''
CLEAN = '''Feature: Collapse whitespace
  Scenario: Collapses spaces between words
    Given the input string is "  a  b  "
    When collapse_whitespace is called
    Then the result should be "a b"
'''


def test_flags_gherkin_escapes():
    problems = lint_bdd(UNSATISFIABLE, PARSE_STEPS)
    assert any("backslash escapes" in p for p in problems)


def test_flags_empty_value_with_parse():
    problems = lint_bdd(EMPTY_VALUE, PARSE_STEPS)
    assert any("empty quoted value" in p for p in problems)


def test_empty_value_is_fine_with_re():
    assert lint_bdd(EMPTY_VALUE, RE_STEPS) == []


def test_clean_contract_passes():
    assert lint_bdd(CLEAN, PARSE_STEPS) == []


def test_escapes_flagged_regardless_of_step_style():
    assert lint_bdd(UNSATISFIABLE, RE_STEPS)
