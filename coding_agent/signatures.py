"""Failure-signature normalisation for the no-progress detector (Phase 2).

CODING_ENGINEER.md §3.4 treats the signature *recipe* as spec, not
implementation detail, because the no-progress detector is only as good as
its normalisation: over-normalise and two genuinely different bugs collapse
into a premature "stall"; under-normalise and the same bug across two edits
looks like progress and the loop runs forever.

    signature = sha1(phase | normalised_test_name | error_class
                     | message_template | top_frame_func)

- phase: self_check | bdd_gate | review (closed set).
- normalised_test_name: pytest nodeid minus the parametrisation suffix
  (test_add[3-5] -> test_add). Keeping the test name is what makes a
  *different* failing test correctly read as progress.
- error_class: exception type.
- message_template: exception message with paths, line numbers, hex
  addresses, durations and timestamps stripped (these churn as the agent
  edits and would otherwise defeat the match). Assertion *values* are
  deliberately NOT stripped -- "expected 3 got 5" vs "expected 4 got 6" are
  different failures.
- top_frame_func: function name only from the innermost in-worktree frame --
  no file, no line number. A tiebreaker so a generic template
  (AssertionError: ...) doesn't over-merge distinct bugs.
"""

from __future__ import annotations

import hashlib
import re

# -- message templating: strip only the things that churn between edits ------

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?")
_DURATION = re.compile(r"\b\d+(?:\.\d+)?\s?(?:s|ms|us|ns)\b")
_HEX = re.compile(r"0x[0-9a-fA-F]+")
_WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s:*?\"<>|]+")
_UNIX_PATH = re.compile(r"(?:/[\w.\-]+)+")
_LINE_REF = re.compile(r":\d+(?::\d+)?")  # ":123" or ":123:45" after a path
_LINE_WORD = re.compile(r"\bline \d+\b", re.IGNORECASE)
_PARAMETRISE = re.compile(r"\[.*\]$")


def normalise_test_name(nodeid: str) -> str:
    """Drop the parametrisation suffix so test_add[3-5] and test_add[1-1]
    share a signature but stay distinct from test_subtract."""
    return _PARAMETRISE.sub("", (nodeid or "").strip())


def template_message(message: str) -> str:
    """Strip paths / line numbers / hex / durations / timestamps so the same
    logical error keeps one template across edits. Order matters: timestamps
    and durations before the generic path/line passes so their digits aren't
    half-eaten first."""
    s = message or ""
    s = _TIMESTAMP.sub("<ts>", s)
    s = _DURATION.sub("<dur>", s)
    s = _HEX.sub("<hex>", s)
    s = _WIN_PATH.sub("<path>", s)
    s = _UNIX_PATH.sub("<path>", s)
    s = _LINE_REF.sub(":<n>", s)
    s = _LINE_WORD.sub("line <n>", s)
    return s.strip()


def compute_signature(
    phase: str,
    test_name: str | None,
    error_class: str | None,
    message_template: str | None,
    top_frame_func: str | None,
) -> str:
    raw = "|".join(
        [phase, test_name or "", error_class or "", message_template or "", top_frame_func or ""]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # id, not security


def review_signature(location: str, severity: str) -> str:
    """Reviewer rejections are signed too (§3.4): (review, location, severity)
    per blocking finding, so a maker/checker stalemate is caught by the same
    no-progress rule. Wired in Phase 3 when the reviewer exists; defined here
    so the recipe lives in one place."""
    raw = "|".join(["review", location or "", severity or ""])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # id, not security


# -- pulling a signable failure out of a pytest-json-report ------------------

_ERROR_CLASS = re.compile(r"^([A-Za-z_][\w.]*Error|[A-Za-z_][\w.]*Exception|AssertionError|Failed)\b")
_FRAME_FUNC = re.compile(r"\.py:\d+: in (\w+)")
_FILE_FRAME_FUNC = re.compile(r'File \"[^\"]+\", line \d+, in (\w+)')


def _error_class_from_message(message: str) -> str:
    """Best-effort exception type from a crash message like
    'AssertionError: expected 3 got 5'. pytest-json-report doesn't hand us the
    class as a separate field, so we read the leading token."""
    if not message:
        return ""
    head = message.strip().splitlines()[0]
    m = _ERROR_CLASS.match(head)
    if m:
        return m.group(1)
    # Fall back to the text before the first colon if it looks like a type.
    before = head.split(":", 1)[0].strip()
    return before if before and " " not in before else ""


def _top_frame_func(longrepr: str) -> str:
    """Innermost frame's function name from a pytest longrepr string. pytest
    renders frames in outer->inner order, so the LAST match is the innermost.
    Handles both pytest's short style (`file.py:12: in func`) and the classic
    `File "...", line 12, in func` style."""
    if not longrepr:
        return ""
    matches = _FRAME_FUNC.findall(longrepr) or _FILE_FRAME_FUNC.findall(longrepr)
    return matches[-1] if matches else ""


def extract_failures(report: dict) -> list[dict]:
    """Failing tests from a pytest-json-report dict, each as
    {nodeid, error_class, message, top_frame_func}. Ordered as the report
    lists them, so callers can take the first deterministically. Empty list
    if the report has no failing tests (e.g. a ruff-only self_check failure,
    or pytest exit 5)."""
    out: list[dict] = []
    for test in report.get("tests", []) or []:
        if test.get("outcome") not in ("failed", "error"):
            continue
        # The crash/longrepr live under whichever phase failed (usually call,
        # but a collection/import error surfaces under setup).
        call = test.get("call") or test.get("setup") or {}
        crash = call.get("crash") or {}
        message = crash.get("message") or ""
        longrepr = call.get("longrepr") or test.get("longrepr") or ""
        out.append(
            {
                "nodeid": test.get("nodeid", ""),
                "error_class": _error_class_from_message(message),
                "message": message,
                "top_frame_func": _top_frame_func(longrepr if isinstance(longrepr, str) else ""),
            }
        )
    return out


def signature_for_failure(phase: str, failure: dict) -> str:
    """sha1 signature for one extracted failure dict (from extract_failures)."""
    return compute_signature(
        phase,
        normalise_test_name(failure.get("nodeid", "")),
        failure.get("error_class", ""),
        template_message(failure.get("message", "")),
        failure.get("top_frame_func", ""),
    )
