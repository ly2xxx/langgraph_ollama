"""String Calculator kata — deliberately incomplete.

This is the Phase-0/Phase-1 demo fixture for the Coding Engineer agent
(see coding_agent/CODING_ENGINEER.md). The spec lives in
features/calculator.feature, not here — `add()` is left unimplemented so
every scenario in that feature file fails for a real reason (NotImplementedError),
not a trivial or accidental one, until an agent (or a person) implements it.
"""


def add(numbers: str) -> int:
    """Sum the numbers in a delimited string.

    See features/calculator.feature for the full behavioural spec:
    empty string, single number, comma-separated numbers, an unknown
    amount of numbers, newline as an additional delimiter, and negative
    numbers raising an error that lists all of them.
    """
    raise NotImplementedError("add() is not implemented yet")
