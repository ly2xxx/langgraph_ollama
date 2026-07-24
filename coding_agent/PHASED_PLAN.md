# PHASED_PLAN — Coding Engineer implementation log

Companion to `CODING_ENGINEER.md`: that document is the design, this one is
the build log — updated at the end of each phase with what was actually
implemented, how it was verified, and where reality forced a small
deviation from the plan. Read `CODING_ENGINEER.md` first; this fills in
"what exists right now."

---

## Phase 0 — Scaffolding ✅

**Delivered:** `coding_agent/tools/code_exec.py` (filesystem jail + allowlisted
command runner), `coding_agent/tools/worktree.py` (git-worktree isolation +
non-git fallback), `coding_agent/models.py` (`get_llm(role)` primary/secondary
seam), `coding_agent/sample_target/` (string-calculator kata fixture), 32 unit
tests, `pyproject.toml`/`.env.example` updates.

**Verified:** all 32 unit tests pass; the kata fixture was confirmed to fail
*genuinely* (real assertion failures, not collection errors) with the stub,
and to pass 6/6 with a throwaway correct implementation dropped in and
removed again.

**Bugs caught during verification (not just happy-path checks):**
- `worktree.diff()` originally used plain `git diff HEAD`, which is blind to
  brand-new untracked files — fixed with an `add -A -N` (intent-to-add) step
  before diffing.
- The BDD step `parsers.parse('the string "{value}"')` can't match an empty
  capture, so the empty-string scenario failed on step lookup instead of on
  the real assertion — switched to `parsers.re(r'the string "(?P<value>.*)"')`.

**Verification environment note:** tests ran in a throwaway sandbox `pip`
venv (Python 3.10), not the project's real `uv`-managed environment (which
targets Python ≥3.12 per `pyproject.toml`) — the sandbox has no access to the
user's Windows machine or its Ollama server. `uv sync` on the real machine is
still required to pick up the new dependencies.

---

## Phase 1 — Linear loop ✅

**Delivered:** the full graph — `intake → author_bdd → plan_tot (single
fixed plan) → code → self_check → bdd_gate → diagnose (stub) → finalize /
escalate` — wired in `coding_agent/engine.py`, plus `coding_agent/schemas.py`
(pydantic structured-output contracts), `coding_agent/prompts.py`,
`coding_agent/report.py` (run-report + state-snapshot writer), and 7
end-to-end integration tests in `coding_agent/tests/test_engine.py`.

**Scope, per CODING_ENGINEER.md §6:** no plan-switching (ToT/GoT is Phase 3),
no signature-based no-progress detection or two-plans-exhausted hard exit
(Phase 2), no adversarial reviewer (Phase 3). `diagnose` is a stub: it counts
attempts against budgets and logs a plain-text failure summary (no LLM
classification, no `failure_signature`), and routes retry-vs-escalate on
that basis alone.

**What does and doesn't call an LLM in Phase 1:**
- `intake` — real LLM call (structured `TargetSpec` output), via the
  `_llm_parse_target_spec` boundary function.
- `author_bdd` — **no LLM call** for the sample_target demo: it first scans
  the worktree for existing `*.feature` files and adopts them as-is if
  found (sample_target ships one), only falling back to LLM generation via
  `_llm_author_bdd` when none exist. This wasn't explicitly speced in
  CODING_ENGINEER.md §3.3 (which describes author_bdd as always drafting);
  adding the adopt-if-present check avoids the agent overwriting a
  carefully-designed existing spec with a possibly worse one, and matches
  how the Phase 1 demo goal is phrased ("...so all scenarios in
  features/calculator.feature pass" — implying the feature file is already
  there).
- `code` (maker) — real LLM call via `_run_maker` (a `create_tool_calling_agent`
  + `AgentExecutor`, matching the pattern already used in `web_researcher.py`).
- `self_check` / `bdd_gate` — no LLM, real `pytest`/`ruff` subprocesses.

**Testing strategy:** integration tests monkeypatch exactly the three LLM
boundary functions (`_llm_parse_target_spec`, `_llm_author_bdd`, `_run_maker`)
and run everything else for real — actual worktree creation, actual
`pytest`/`ruff` subprocess gates, actual git commits, actual report writing.
This was a deliberate choice over mocking at the `get_llm()`/`ChatOllama`
level: it proves the orchestration (retries, budgets, escalation, commits)
is correct without needing a live model, while leaving the model-facing
prompts themselves to be validated in a real run against Ollama (not
possible from this sandbox — see below). 39/39 tests pass (32 from Phase 0
+ 7 new), including a full CLI smoke test (`python -m coding_agent.engine`
equivalent) that produced a real run-report.md and a clean diff implementing
the kata.

**Bugs caught during verification:**
- `self_check`'s original `ruff check .` runs with `cwd` inside the target
  *worktree*, which sits outside this repo's directory tree — so this
  project's own `pyproject.toml` `[tool.ruff]` config never applies there.
  Against a target whose filesystem quirks we don't control (in the sandbox,
  every file reports the executable bit due to the mount, tripping `EXE002`
  for reasons with nothing to do with code quality), an unscoped `ruff
  check .` isn't a reliable fast gate. Fixed by pinning `self_check`'s ruff
  invocation to `--select E9,F` (syntax errors + pyflakes) explicitly,
  regardless of what config the target does or doesn't have — this is also
  arguably more correct for a "fast maker self-check" than a full style
  audit.
- `pytest` legitimately exits 5 ("no tests collected") when `self_check`'s
  scope excludes the frozen BDD directory and the target has no other
  tests (true for the kata fixture). Treated as a pass for `self_check`
  specifically (not `bdd_gate`, which must always find and run something).

**Deviations from CODING_ENGINEER.md — schema additions.** Three
`CodingLoopState` fields exist in the implementation that §3.2 didn't
explicitly define a home for; each is small and backward-compatible:
- `escalation_reason: str | None` — `escalate`'s reason (§3.3: "the reason
  (budget | no-progress | unsuitable goal)") has to live somewhere in state
  to reach the report writer.
- `run_started_at: float` — the wall-clock budget (§3.4 hard exit #4) needs
  a start time to compare elapsed time against.
- `is_fallback_copy: bool` — `finalize`/`escalate` reconstruct a
  `WorktreeHandle` from state to call `commit()`/`diff()`, and that
  dataclass has this field (§3.3, `worktree.py`); it has to be threaded
  through from `intake`.

**Deviation — maker tool surface.** `Jail` supports `apply_patch`, `delete_file`,
and `move_file`, and `run_command` supports more than `pytest`; Phase 1's
`_build_maker_tools` only exposes `read_file`, `list_dir`, `write_file`, and a
scoped `run_pytest` convenience tool to the LLM agent. This is a deliberate
scope trim, not an oversight — `write_file` (whole-file replace) covers the
kata-sized changes Phase 1 targets, and a narrower tool surface is less for a
local model to get wrong. Expanding it is a small, low-risk follow-up
whenever a target needs deletes/moves/other commands.

**Deviation — ruff config.** Added `[tool.ruff]` to the project's own
`pyproject.toml` (`target-version = "py312"`, `ignore = ["EXE002", "UP017"]`)
for *this project's* lint runs — not related to the `self_check` fix above,
which is a separate, target-scoped concern. `UP017` (prefer `datetime.UTC`
over `datetime.timezone.utc`) is ignored because `timezone.utc` is
identical in behaviour and was kept for compatibility with the Python 3.10
sandbox this was verified in, even though the project's real floor is 3.12.

**Not yet exercised:** the optional `author_bdd` HITL interrupt
(`CODING_AGENT_HITL_BDD_APPROVAL`) is fully implemented (uses
`langgraph.types.interrupt`, confirmed importable on the pinned `langgraph`
version) but not covered by a test yet — Phase 2's acceptance criteria
explicitly calls for testing both the pause-on-ambiguous and
don't-pause-on-clear paths with resume, which needs a bit more test
infrastructure (driving the graph through an `__interrupt__` and resuming
with `Command(resume=...)`) than Phase 1 needed. Also not yet tested: a
real live-model run against Ollama (the sandbox can't reach the user's
Windows machine) — everything here is verified with the LLM boundary
functions mocked. A live run is the natural first thing to try once this
lands, to sanity-check the actual prompts.

---

## What's next — Phase 2

Per `CODING_ENGINEER.md` §6: replace the `diagnose` stub with real
signature-based no-progress detection (§3.4's `sha1(phase | test_name |
error_class | message_template | top_frame_func)` recipe), the two-plans-
exhausted hard exit (moot until Phase 3 adds a second plan, but the
single-plan budget-exhaustion path already implemented here is the Phase 2
starting point), and tests for the stop-flag (already implemented and
tested in Phase 1) plus the `author_bdd` interrupt/resume path.
