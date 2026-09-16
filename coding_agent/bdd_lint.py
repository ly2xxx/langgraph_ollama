"""Catch BDD contracts that cannot be satisfied, BEFORE they are frozen.

Run 20260916T174956 burned all three attempts and escalated with
`two_plans_exhausted` without ever editing the source file. The drafted feature
contained scenarios no implementation could pass, and because the contract is
frozen the agent could not fix the real problem -- it re-diagnosed "test-logic"
three times and got the identical failure signature each time.

Both traps below are mechanical, so they are checked mechanically rather than
left to the prompt alone.
"""
from __future__ import annotations

import re

# A step line's quoted value, e.g.  Given the input string is "a\t\nb"
_STEP_LINE = re.compile(r'^\s*(Given|When|Then|And|But)\s+.*?"([^"]*)"', re.I)
# Escape sequences Gherkin does NOT interpret -- they arrive as literal chars.
_ESCAPE = re.compile(r'\\[tnr]')
_PARSE_DECORATOR = re.compile(r'parsers\.parse\(')


def lint_bdd(feature_text: str, steps_text: str = "") -> list[str]:
    """Return human-readable problems; empty list means the contract is sane."""
    problems: list[str] = []

    escaped: list[str] = []
    empty_valued: list[str] = []
    for i, line in enumerate(feature_text.splitlines(), start=1):
        m = _STEP_LINE.match(line)
        if not m:
            continue
        value = m.group(2)
        if _ESCAPE.search(value):
            escaped.append(f"line {i}: {line.strip()}")
        if value == "":
            empty_valued.append(f"line {i}: {line.strip()}")

    if escaped:
        problems.append(
            "Gherkin does not interpret backslash escapes: \\t and \\n reach the step "
            "as the two literal characters, not a tab or newline, so these scenarios "
            "cannot pass under ANY implementation:\n  "
            + "\n  ".join(escaped)
            + "\nExpress whitespace in prose instead -- e.g. "
            'Given the input string is "a" and "b" separated by a tab -- and build the '
            "value in the step definition."
        )

    if empty_valued and _PARSE_DECORATOR.search(steps_text):
        problems.append(
            'parsers.parse() cannot match an empty quoted value: "{param}" requires at '
            "least one character, so these steps raise StepDefinitionNotFoundError:\n  "
            + "\n  ".join(empty_valued)
            + "\nUse parsers.re(r'... \"(?P<name>[^\"]*)\" ...') for any step whose value "
            "may be empty."
        )

    return problems
