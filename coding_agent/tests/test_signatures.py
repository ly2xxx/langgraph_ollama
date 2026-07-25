"""Unit tests for coding_agent.signatures -- the no-progress detector's
normalisation recipe (CODING_ENGINEER.md §3.4). These pin the behaviour the
recipe promises: stable across the churn an edit produces, distinct across
genuinely different failures."""

from coding_agent.signatures import (
    compute_signature,
    extract_failures,
    normalise_test_name,
    signature_for_failure,
    template_message,
)


def test_normalise_strips_parametrisation_only():
    assert normalise_test_name("t/test_x.py::test_add[3-5]") == "t/test_x.py::test_add"
    assert normalise_test_name("t/test_x.py::test_add[1-1]") == "t/test_x.py::test_add"
    # a different test stays different -- that's what reads as progress.
    assert normalise_test_name("t/test_x.py::test_sub") != normalise_test_name("t/test_x.py::test_add")


def test_template_strips_churn_but_keeps_assertion_values():
    a = template_message('File "/abs/worktree/mod.py", line 42, in f\nAssertionError: expected 3 got 5')
    b = template_message('File "/other/path/mod.py", line 99, in f\nAssertionError: expected 3 got 5')
    # paths + line numbers churn between edits -> must not affect the template.
    assert a == b
    # but the assertion values are the failure's identity -> preserved.
    assert "3" in a and "5" in a


def test_template_distinguishes_different_assertion_values():
    a = template_message("AssertionError: expected 3 got 5")
    b = template_message("AssertionError: expected 4 got 6")
    assert a != b


def test_template_strips_hex_and_timestamps_and_durations():
    t = template_message("boom at 0xdeadbeef on 2026-07-25T08:21:00 after 1.5s")
    assert "0xdeadbeef" not in t
    assert "2026-07-25" not in t
    assert "1.5s" not in t


def test_signature_is_stable_across_line_and_path_churn():
    f1 = {
        "nodeid": "t/test_x.py::test_add[3-5]",
        "error_class": "AssertionError",
        "message": 'File "/a/mod.py", line 42, in add\nAssertionError: expected 8 got 0',
        "top_frame_func": "add",
    }
    f2 = {  # same bug, file moved + line shifted after an edit
        "nodeid": "t/test_x.py::test_add[1-2]",
        "error_class": "AssertionError",
        "message": 'File "/b/pkg/mod.py", line 7, in add\nAssertionError: expected 8 got 0',
        "top_frame_func": "add",
    }
    assert signature_for_failure("bdd_gate", f1) == signature_for_failure("bdd_gate", f2)


def test_signature_differs_by_phase_and_test():
    base = {"nodeid": "t::test_a", "error_class": "AssertionError", "message": "x", "top_frame_func": "f"}
    other_test = {**base, "nodeid": "t::test_b"}
    assert signature_for_failure("self_check", base) != signature_for_failure("bdd_gate", base)
    assert signature_for_failure("bdd_gate", base) != signature_for_failure("bdd_gate", other_test)


def test_top_frame_func_disambiguates_same_template():
    a = {"nodeid": "t::test_a", "error_class": "AssertionError", "message": "boom", "top_frame_func": "add"}
    b = {"nodeid": "t::test_a", "error_class": "AssertionError", "message": "boom", "top_frame_func": "subtract"}
    assert signature_for_failure("bdd_gate", a) != signature_for_failure("bdd_gate", b)


def test_extract_failures_from_pytest_json_report():
    report = {
        "tests": [
            {"nodeid": "t::test_ok", "outcome": "passed"},
            {
                "nodeid": "t::test_bad",
                "outcome": "failed",
                "call": {
                    "crash": {"message": "AssertionError: expected 3 got 5"},
                    "longrepr": "t/test_x.py:12: in test_bad\n    assert add('1,2') == 3\nE   AssertionError: expected 3 got 5",
                },
            },
        ]
    }
    failures = extract_failures(report)
    assert len(failures) == 1
    assert failures[0]["nodeid"] == "t::test_bad"
    assert failures[0]["error_class"] == "AssertionError"
    assert failures[0]["top_frame_func"] == "test_bad"


def test_extract_failures_empty_when_all_pass():
    assert extract_failures({"tests": [{"nodeid": "t::a", "outcome": "passed"}]}) == []
    assert extract_failures({}) == []


def test_compute_signature_is_deterministic_hex():
    s1 = compute_signature("bdd_gate", "t::a", "AssertionError", "boom", "f")
    s2 = compute_signature("bdd_gate", "t::a", "AssertionError", "boom", "f")
    assert s1 == s2
    assert len(s1) == 40 and all(c in "0123456789abcdef" for c in s1)
