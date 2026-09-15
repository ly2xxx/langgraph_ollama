#!/usr/bin/env python3
"""Preflight for the LLM layer: find out WHICH layer is failing, in ~20 seconds.

The gateway logging a success only means the HTTP call returned 200. Structured
output can still fail client-side, and that is invisible in LiteLLM's logs. This
walks the stack bottom-up and reports the first layer that breaks.

    uv run python -m evals.diagnose_llm

Exit code 0 if every layer passes, 1 otherwise.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402


class Tiny(BaseModel):
    """Deliberately minimal — if this cannot be produced, nothing bigger will."""
    answer: str = Field(description="the single word 'yes'")
    count: int = Field(description="the number 42")


def _ok(label: str, detail: str = "") -> None:
    print(f"  [PASS] {label}" + (f"  {detail}" if detail else ""))


def _fail(label: str, exc: BaseException) -> None:
    print(f"  [FAIL] {label}")
    print(f"         {type(exc).__name__}: {str(exc)[:400]}")


def main() -> int:
    failures: list[str] = []

    # ---- Layer 0: resolved configuration -------------------------------------
    print("\n0. Resolved model config (secrets omitted)")
    try:
        from coding_agent.models import describe_all, get_llm
        info = describe_all()
        for role, cfg in info.items():
            print(f"     {role:10s} provider={cfg.get('provider')!r} "
                  f"model={cfg.get('model')!r} base_url={cfg.get('base_url')!r}")
        for role, cfg in info.items():
            if not cfg.get("model"):
                print(f"  [FAIL] {role}: no model resolved — set OPENAI_MODEL or "
                      f"CODING_AGENT_{role.upper()}_MODEL")
                failures.append(f"{role}:no-model")
        if not failures:
            _ok("config resolved")
    except Exception as exc:
        _fail("config", exc)
        traceback.print_exc()
        return 1

    for role in ("primary", "secondary"):
        print(f"\n--- role: {role} ---")
        try:
            llm = get_llm(role)
        except Exception as exc:
            _fail(f"{role}: get_llm()", exc)
            failures.append(f"{role}:get_llm")
            continue

        # ---- Layer 1: plain chat ---------------------------------------------
        try:
            resp = llm.invoke("Reply with exactly: OK")
            text = getattr(resp, "content", str(resp))
            _ok("1. plain chat", f"-> {str(text)[:60]!r}")
        except Exception as exc:
            _fail("1. plain chat", exc)
            failures.append(f"{role}:chat")
            continue  # nothing below can work

        # ---- Layer 2: each structured-output method separately ---------------
        # This is the layer LiteLLM's logs cannot tell you about.
        from coding_agent.structured import _methods_for
        method_ok = []
        for method in _methods_for(llm):
            try:
                bound = llm.with_structured_output(Tiny, method=method)
            except Exception as exc:
                _fail(f"2. with_structured_output(method={method!r}) — binding", exc)
                continue
            try:
                out = bound.invoke("Answer 'yes' and the number 42.")
                if out is None:
                    _fail(f"2. method={method!r} — returned None",
                          ValueError("provider returned no parseable object"))
                    continue
                _ok(f"2. method={method!r}", f"-> {out!r}")
                method_ok.append(method)
            except Exception as exc:
                _fail(f"2. method={method!r} — invoke", exc)

        if not method_ok:
            print(f"  >>> NO structured-output method works for {role}.")
            print(f"  >>> This is almost certainly your failure: the gateway returns 200,")
            print(f"  >>> the parse fails here, invoke_structured() exhausts its ladder")
            print(f"  >>> and raises StructuredOutputError.")
            failures.append(f"{role}:no-structured-method")
        else:
            print(f"  working method(s) for {role}: {method_ok}")

        # ---- Layer 3: the real wrapper the agent uses ------------------------
        try:
            from coding_agent.structured import invoke_structured
            out = invoke_structured(llm, Tiny, "Answer 'yes' and the number 42.")
            _ok("3. invoke_structured()", f"-> {out!r}")
        except Exception as exc:
            _fail("3. invoke_structured()", exc)
            failures.append(f"{role}:invoke_structured")

    print("\n" + "=" * 62)
    if failures:
        print(f"  FAILED layers: {', '.join(failures)}")
        print("  Fix the lowest-numbered failing layer first; the ones above it")
        print("  cannot pass until it does.")
        print("=" * 62)
        return 1
    print("  All layers pass. The LLM stack is not your problem —")
    print("  re-run `python -m evals.runner --tasks bug-001 --keep` and send the traceback.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
