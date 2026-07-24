"""Unit tests for coding_agent.structured — the robust structured-output
wrapper added after the first live run failed on an OutputParserException
(model answered in markdown instead of JSON). See structured.py's module
docstring and PHASED_PLAN.md "live-run fixes"."""

import pytest
from pydantic import BaseModel

from coding_agent.structured import StructuredOutputError, invoke_structured


class Toy(BaseModel):
    value: int


class _FakeRunnable:
    """Scripted runnable: pops the next behaviour off a list. 'raise' raises
    a parse-like error, 'none' returns None, anything else is returned."""

    def __init__(self, script, calls):
        self.script = script
        self.calls = calls

    def invoke(self, prompt):
        self.calls.append(prompt)
        action = self.script.pop(0)
        if action == "raise":
            raise ValueError("Invalid json output: **value**: 7")
        if action == "none":
            return None
        return action


class _FakeLLM:
    """Fake chat model whose with_structured_output supports a configurable
    set of methods, each with its own scripted behaviour list."""

    def __init__(self, methods_scripts):
        self.methods_scripts = methods_scripts
        self.calls_by_method = {m: [] for m in methods_scripts}

    def with_structured_output(self, schema, method=None, **kwargs):
        if method not in self.methods_scripts:
            raise TypeError(f"method {method!r} not supported")
        return _FakeRunnable(self.methods_scripts[method], self.calls_by_method[method])


def test_first_method_success_is_returned_directly():
    llm = _FakeLLM({"json_schema": [Toy(value=1)], "function_calling": []})
    result = invoke_structured(llm, Toy, "prompt")
    assert result == Toy(value=1)
    assert len(llm.calls_by_method["json_schema"]) == 1
    assert len(llm.calls_by_method["function_calling"]) == 0  # never reached


def test_parse_error_retries_with_error_fed_back():
    llm = _FakeLLM({"json_schema": ["raise", Toy(value=2)], "function_calling": []})
    result = invoke_structured(llm, Toy, "prompt")
    assert result == Toy(value=2)
    calls = llm.calls_by_method["json_schema"]
    assert len(calls) == 2
    assert calls[0] == "prompt"
    assert "could not be parsed" in calls[1]  # retry prompt carries the error
    assert "Invalid json output" in calls[1]


def test_unsupported_method_falls_back_to_next():
    # json_schema unsupported entirely -> falls through to function_calling.
    llm = _FakeLLM({"function_calling": [Toy(value=3)]})
    result = invoke_structured(llm, Toy, "prompt")
    assert result == Toy(value=3)


def test_none_result_is_retried_not_returned():
    llm = _FakeLLM({"json_schema": ["none", Toy(value=4)], "function_calling": []})
    result = invoke_structured(llm, Toy, "prompt")
    assert result == Toy(value=4)


def test_all_methods_exhausted_raises_structured_output_error():
    llm = _FakeLLM({"json_schema": ["raise", "raise"], "function_calling": ["raise", "raise"]})
    with pytest.raises(StructuredOutputError) as excinfo:
        invoke_structured(llm, Toy, "prompt")
    assert "Toy" in str(excinfo.value)
    # 2 attempts per method x 2 methods
    assert len(llm.calls_by_method["json_schema"]) == 2
    assert len(llm.calls_by_method["function_calling"]) == 2
