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

## Phase 1 follow-up — self-hosting fixes ✅

Prompted by a real target: refactoring `rag_research_chatbot.py` into a
subfolder within this same repo, as a POC. Two Phase 1 scope-trims turned
out to matter for that specific shape of task, plus one hygiene gap they
exposed. None of these needed Phase 2/3 sophistication — they're small,
targeted fixes to Phase 1 code.

1. **Maker can now delete and move files.** `_build_maker_tools` exposes
   `delete_file`/`move_file` (wrapping `Jail` methods that already existed
   and were already unit-tested from Phase 0) alongside `write_file`.
   Without this, a "move" would leave the old file behind as a stray
   duplicate — `write_file` alone never removes anything. `MAKER_SYSTEM_PROMPT`
   was updated to say so explicitly, including that the maker should update
   *other* files that reference what it moved (e.g. an import), not just the
   file named in the goal.
2. **self_check/bdd_gate exclude `coding_agent/` when present in the target.**
   New `_harness_exclude_dirs()` helper: if the worktree contains a
   `coding_agent` directory (true only when self-hosting — pointing the
   agent at its own repo), it's excluded from both ruff's and pytest's scope
   in both gates. Without this, any goal run against this repo would also
   execute the agent's own ~40-test suite as a side effect, which is slow
   and has nothing to do with whatever the actual goal is.
3. **`.loop/` added to `.gitignore`.** Self-hosting means the loop's own
   runtime state (worktrees, sqlite checkpoints, run reports) lands inside
   the same repo it's operating on; without a gitignore entry, `.loop/`
   would show up as untracked clutter in `git status` and risk being swept
   into a human's own `git add -A`.

**Verified:** a new integration test (`test_maker_can_move_a_module_and_fix_the_import`)
runs the exact shape of the POC through the full graph — mocked maker
relocates `calculator.py` into `sub/`, fixes the one file that imports it
(the pytest-bdd step defs — not frozen, since only the `.feature` file is
per §3.3/§4), and deletes the original — and asserts the run finishes
`done` with a diff showing a clean removal-plus-addition, not a duplicate.
A second test confirms a nested `coding_agent/tests/` with an intentionally
failing test doesn't affect `self_check`'s outcome. 42/42 tests pass overall.

**Still true regardless of these fixes:** `rag_research_chatbot.py` and
`app.py` have no existing test coverage, so the BDD scenarios `author_bdd`
drafts are the *only* safety net catching a broken cross-file import — nothing
else would notice if, say, `app.py`'s import of `RAGResearchChatbot` silently
broke. Worth either enabling `CODING_AGENT_HITL_BDD_APPROVAL=true` for this
specific run to review the drafted scenarios before they freeze, or writing
one BDD scenario by hand up front (e.g. "importing app and constructing
RAGResearchChatbot does not raise"). A Phase 3 adversarial reviewer would
also help catch this, but doesn't exist yet.

---

## Phase 1 follow-up — minimal app.py entry point ✅

Prompted by the same POC: there was no way to run the agent except the CLI
(`python -m coding_agent.engine`). Added a lightweight Streamlit access
point rather than waiting for full Phase 4 polish (§5's budgets expander,
diff viewer, demo queries, telemetry wiring — none of that is here yet):

- `ui/coding_engineer_panel.py` — `render_coding_engineer_panel()`: target-dir
  text input, goal textarea, an "ambiguous scenarios pause" checkbox
  (defaults on), a Run button, live per-node status via `st.status`, and the
  run report rendered in an expander when done.
- `app.py` — added `CODING_ENGINEER` to the assistant selectbox; selecting it
  branches early (before the model-selection/`build_chain` machinery, which
  doesn't apply here — `coding_agent.models` resolves its own primary/secondary
  models from env vars) and renders the panel.
- `coding_agent/engine.py` — refactored `run_cli`'s inline streaming loop into
  a reusable `stream_run(run_id, target_dir, goal, hitl, budgets)` generator,
  shared by the CLI and the new panel instead of duplicated. `_new_run_id`
  was renamed to `new_run_id` (dropped the underscore — it's now a
  cross-module public function, not engine.py-private).

**Verified:** full `coding_agent` suite re-run after the `engine.py` refactor
(42/42 still pass — confirms `run_cli`'s behavior is unchanged), `ruff`
clean, both new/changed files syntax-checked, and `ui/coding_engineer_panel.py`
confirmed to import cleanly with `streamlit` installed. **Not verified:** an
actual browser click-through of the Run button — that needs either a live
Ollama connection (unavailable in this sandbox) or mocking the LLM boundary
functions from inside a running Streamlit session, which wasn't attempted.
The underlying `stream_run` path it calls is the same one covered by all the
engine integration tests, so the risk is concentrated in the UI glue code
itself (event loop, `st.status` updates, report rendering) rather than the
agent logic.

---

## Phase 1 follow-up — live-run fixes ✅

The first live run (glm-5.2:cloud via Ollama, targeting the RAG-chatbot
refactor POC) failed in `intake` with an `OutputParserException` that
crashed the whole graph and surfaced as a raw stack trace in the UI. The
model's *content* was excellent — a well-formed spec with sensible
acceptance criteria — but it answered in markdown, and the default
`with_structured_output` (tool-calling based) parser choked. This was
precisely the §7 "local-model structured-output brittleness" risk, whose
promised mitigation ("one retry with the error fed back") Phase 1 had
documented but not actually implemented. Fixes:

1. **`coding_agent/structured.py` — `invoke_structured()`.** Three layers:
   (a) prefer `method="json_schema"`, which langchain-ollama routes through
   Ollama's native `format` parameter so decoding is *constrained* to
   schema-valid JSON — the model can't produce markdown even if inclined
   (verified available on langchain-ollama 0.3.x, the pinned range);
   (b) fall back to the default tool-calling method if json_schema isn't
   supported; (c) within each method, one retry with the parse error fed
   back plus an explicit "ONLY valid JSON" instruction. Exhaustion raises
   `StructuredOutputError`. Both LLM structured-output call sites
   (`_llm_parse_target_spec`, `_llm_author_bdd`) now go through it.
2. **Graceful escalation instead of a crash.** `intake` and `author_bdd`
   catch `StructuredOutputError` and route to `escalate` — run report
   written, reason recorded, UI shows a finished-with-escalation run
   instead of a traceback. `author_bdd → plan_tot` had to become a
   conditional edge for this (it was a plain edge; an escalated status
   would previously have marched straight on into planning).
3. **Pipeline visualization in the panel** (user request, matching the other
   agents): `displayGraph`'s body moved from `app.py` to a shared
   `ui/graph_display.py :: render_graph_diagram()` (same mermaid.ink
   PNG-with-disk-cache behaviour; `app.py`'s `displayGraph` now delegates
   to it), and the Coding Engineer panel renders the graph topology above
   its inputs via an `st.cache_resource`-cached uncheckpointed
   `build_graph()` instance — same pattern as `app.py`'s `build_chain`.

**Verified:** 48/48 tests pass — 5 new unit tests for `invoke_structured`
(method fallback, retry-with-error-fed-back, None-result retry, exhaustion)
using a scripted fake LLM, plus 1 new integration test proving an intake
parse failure now ends in a graceful escalation with a report. Ruff clean.
Panel/graph_display import-checked with streamlit installed. **Still not
verified:** a live browser round-trip (sandbox has no Ollama) — but the
failing path from the user's screenshot is now covered by tests at both
the unit and graph level.

---

## Phase 1 follow-up — second live-run bug: tool arg-schema collision ✅

The `json_schema`/retry fix got past `intake`, but the second live run
failed differently, in `code`: `run_pytest() got an unexpected keyword
argument 'v__args'`. Root cause confirmed by reproducing it directly against
the installed `langchain-core`: `run_pytest`'s parameter was named `args`,
and pydantic's function-wrapping internals (used by `@tool`'s schema
inference) reserve `args`/`kwargs` as synthetic field names for wrapping
Python's own `*args`/`**kwargs`. A real parameter named `args` collides with
that reservation and gets silently renamed to `v__args` in the generated
schema — and its type is coerced from `string` to `array` in the process.
So the tool-calling model, told (correctly, by its own understanding of the
tool) to pass a string, was handed a schema that actually required a list
under a different field name; there was no way for it to succeed. Confirmed
with a two-line repro before and after the fix (`t.args` showed
`{'v__args': {'type': 'array', ...}}` for the old name, `{'pytest_args':
{'type': 'string', ...}}` for the new one).

**Fix:** renamed the parameter to `pytest_args`. **Verified:** a new
regression test checks every maker tool's actual invocation schema (via
`tool.args`, not the underlying Python function) for the reserved-name
collision, and invokes `run_pytest` the way a tool-calling agent would —
through `.invoke({"pytest_args": ...})` — to prove it actually works, not
just that the schema looks right. 49/49 tests pass; ruff clean.

**On "the graph doesn't show":** the panel code was inspected line by line
and no bug was found — `render_graph_diagram` is the same mermaid.ink logic
the other three agents already use (now shared via `ui/graph_display.py`
instead of duplicated), and it degrades to a **collapsed** `st.expander`
titled "... image service unreachable" if the mermaid.ink service can't be
reached, rather than failing loudly. That's the most likely explanation —
worth confirming whether the other three agents' graphs render either,
since they now go through the identical code path. Not something this round
changed or could independently verify without a live browser session.

---

## Phase 1 follow-up — third live-run bug: wrong BDD scenario frozen, plus scope/budget fixes ✅

The third live run (the actual rag-chatbot-refactor POC) got all the way to
`code`, but escalated after 4 identical `self_check` failures. The pasted
run report and progress log surfaced four separate problems, of decreasing
severity:

1. **`author_bdd` froze the wrong feature file — the most serious bug.**
   The run report's "Frozen BDD scenarios" field showed
   `coding_agent/sample_target/features/calculator.feature` — this repo's
   own Phase 0 demo fixture — adopted as the definition of done for an
   unrelated goal (moving `rag_research_chatbot.py`). Root cause: the
   self-hosting fixes two rounds ago added `_harness_exclude_dirs()`
   (excluding `coding_agent/`) to `self_check_node` and `bdd_gate_node`, but
   `author_bdd_node`'s own `rglob("*.feature")` scan was never given the same
   exclusion — an oversight, not a new problem. Since this repo genuinely is
   `coding_agent`'s own target when self-hosting, the unscoped scan always
   found the kata fixture first and adopted it, silently substituting a
   frozen goal the maker could never satisfy for the real one. **Fixed:**
   `author_bdd_node` now filters its scan through `_harness_exclude_dirs()`,
   same as the other two gates.
2. **`self_check`'s ruff gate failed on unrelated pre-existing lint debt.**
   Reproduced directly: `ruff check . --select E9,F --extend-exclude=coding_agent`
   against a mini repro of the user's real `app.py` failed on a **pre-existing
   duplicate `import os`**, nothing to do with the maker's change. Whole-worktree
   scope is fine for the from-scratch kata fixture (nothing pre-exists to trip
   on) but wrong for a real repo the goal only touches part of. **Fixed:** new
   `changed_files(handle)` in `tools/worktree.py` (same intent-to-add diff
   trick as `diff()`) lets `self_check_node` scope ruff to `*.py` files the
   maker actually touched this run, falling back to `.` only if nothing
   changed yet.
3. **Run report gave no visibility into *why* a gate failed.** Diagnosing
   both bugs above required blind reproduction in the sandbox because the
   report only showed a boolean pass/fail plus a one-line lesson. **Fixed:**
   `report.py::render_report()` now includes a "## self_check output" /
   "## bdd_gate output" section with the last 40 lines of the actual
   ruff/pytest stdout+stderr, but only for gates that ran and failed (kept
   out of the happy path so successful reports don't balloon).
4. **The maker renamed `app.py` → `app.py.bak` instead of editing it in
   place.** The diff in the run report showed this alongside the legitimate
   `rag_research_chatbot.py` move. `MAKER_SYSTEM_PROMPT` already said to
   update files that reference a moved module, but didn't say *how* —
   apparently permissive enough for the model to reach for `move_file` on a
   file that wasn't itself the subject of the goal. **Fixed:** prompt now
   explicitly reserves `move_file`/`delete_file` for the file actually being
   relocated, and says any file that merely *references* it should be edited
   in place with `write_file`.

**Also fixed, same root cause as #1 in spirit:** every attempt separately
hit `AgentExecutor`'s `max_iterations=8` ("Agent stopped due to max
iterations") before finishing. A real multi-file refactor — read the
target, write the new module, add an `__init__.py`, delete the old file,
edit the importing file, run a self-check — doesn't comfortably fit in 8
tool calls the way the single-file kata does. Raised to `max_iterations=20`.

**Verified:** a new regression test,
`test_author_bdd_excludes_nested_coding_agent_dir`, plants a decoy
`coding_agent/sample_target/features/calculator.feature` inside the target
(mirroring the exact self-hosting shape that caused bug #1) and asserts
`author_bdd` adopts only the target's real, top-level feature file. Full
suite: 50/50 pass. `ruff check coding_agent ui/coding_engineer_panel.py
ui/graph_display.py` clean, both with `--select E9,F` and the project's
default rule set. **Not yet verified:** a fifth live run against Ollama —
the sandbox has no path to the user's machine, so the fix for the
`app.py.bak` rename in particular (a prompt-wording change, not something a
mocked-maker test can meaningfully exercise) is confirmed correct in
reasoning and consistent with the observed failure, but not proven against
a live model yet.

---

## Phase 1 follow-up — log the resolved model before/during a run ✅

Asked directly: log which model a run uses, or let the user pick one like
the other three agents do. Picking would mean threading a model override
from the panel through `get_llm()`/`CodingLoopState` into every LLM call
site — a bigger, riskier change for what the other agents' "picker" mostly
amounts to today (a selectbox around a single `OLLAMA_MODEL` env value).
Logging was the smaller, lower-risk change and was already half-built:
`models.py::describe(role)` existed since Phase 0 (its own docstring said
"used by the UI / run report") but nothing had actually called it yet.

**Delivered:**
- `models.py::describe_all()` — `describe()` for both roles in one call, so
  the CLI, panel, and report all answer "what model is this run using" the
  same way instead of three hand-rolled dicts.
- `stream_run` resolves it once up front and stores it in
  `CodingLoopState["model_info"]` (new field), so a run's report reflects
  what it actually used even if env vars change before the next run.
- `run_cli` prints primary/secondary model+provider before starting.
- The panel shows a caption with both resolved models above the Run button.
- `report.py::render_report()` gained a "## Models" section (only when
  `model_info` is present in state — integration tests that drive the graph
  directly via `graph.invoke()`, bypassing `stream_run`, simply won't have
  it, and the section is skipped rather than printing "None").

**Verified:** new `test_describe_all_reports_both_roles` (models),
`test_render_report_includes_models_section_when_present` /
`..._omits_..._when_absent` (report.py, isolated from the full graph). Full
suite: 53/53 pass (50 + 3 new). Ruff clean, both `--select E9,F` and the
default rule set.

---

## Phase 1 follow-up — self_check gated on debt in a file the maker *had* to touch, + a UI crash ✅

Fourth live run of the POC. The maker actually succeeded — its own messages
across attempts said "All 6 BDD scenarios pass" and "the move is complete
and verified" — but the run still escalated after 4 attempts, all failing
at `self_check`, and then the panel *crashed* trying to display the report.
Two distinct bugs:

1. **`self_check`'s changed-files ruff scoping wasn't enough.** The previous
   round scoped ruff to files the maker changed, which fixes the case where
   pre-existing debt lives in a file the maker never touched. But this goal
   *requires* editing `app.py` (its import of the moved module), and `app.py`
   already carried an unrelated duplicate `import os` (F811/F401). So `app.py`
   was legitimately in scope, and its pre-existing debt failed the gate every
   time — before `bdd_gate` ever got to confirm the BDD scenarios the maker
   kept (correctly) saying passed. **Fixed** with a differential check: ruff
   now runs with `--output-format json` on the changed files, and separately
   on their **baseline (HEAD) versions** (materialised into a temp dir via a
   new `worktree.file_at_baseline()`), and only findings the maker
   *introduced this run* — compared per `(relative-path, rule-code)` so line
   shifts from the edit don't matter — fail the gate. Pre-existing findings
   are forgiven; a genuinely new problem (or any finding in a brand-new file,
   which has no baseline) still fails. Falls back to the old opaque rc check
   if ruff's json can't be parsed, so a broken invocation fails safe rather
   than silently passing. New helpers: `_run_ruff_json`, `_ruff_new_findings`,
   `_render_ruff_findings` in engine.py.
2. **The panel crashed with `UnicodeDecodeError` reading the report.**
   `report.py` writes the run report as utf-8 (it contains em-dashes, arrows,
   the ✅/⏸️ glyphs), but `ui/coding_engineer_panel.py` read it back with a
   bare `Path.read_text()`, which uses the platform default encoding — cp1252
   on the user's Windows machine — and blew up on the first non-latin-1 byte.
   The escalation itself was already handled gracefully; it was only the
   *display* of the resulting report that crashed. **Fixed** by pinning
   `read_text(encoding="utf-8")` (the only production `read_text()` without an
   explicit encoding; the rest are in tests).

**Verified:** two new engine tests —
`test_self_check_forgives_preexisting_lint_debt` (ships `helper.py` with a
duplicate `import os`, has the mocked maker implement the kata *and* append a
line to `helper.py`, asserts the run finishes `done` because the pre-existing
F811/F401 are forgiven) and `test_self_check_fails_on_newly_introduced_finding`
(maker writes a working calculator but with a new unused `import sys`; asserts
the run escalates and the report's ruff output names `F401` — proving the gate
still blocks on introduced debt, i.e. the fix doesn't just disable the check).
Full suite: 55/55 pass. Ruff clean (`--select E9,F` and default). **Still not
verified:** a fifth live run — but the differential logic is exercised in both
directions by the new tests against real ruff/git subprocesses, and the
encoding crash was a deterministic platform-encoding bug with an unambiguous
fix.

---

## Phase 1 follow-up — differential ruff missed two cases: moved files & re-export __init__.py ✅

Fifth live run. The UI crash was gone (report displayed fine) and the maker
again reported success every attempt ("All 7 BDD scenarios pass"), but
self_check *still* failed 4x. The differential-ruff fix from the previous
round was correct in principle but had two blind spots, both specific to the
exact shape of a "move a module into a new package" goal:

1. **A moved file has no baseline at its NEW path.** The differential looked
   up each changed file's baseline via `git show HEAD:<current_path>`. For
   `rag_agent/rag_research_chatbot.py` — moved from the repo root — there's no
   blob at that path in HEAD, so the lookup returned nothing and *every*
   pyflakes finding in the relocated file (the original file carried some)
   read as "introduced this run". **Fixed** with rename detection: new
   `worktree.renamed_paths()` runs `git diff --name-status -M HEAD` (with
   intent-to-add so the uncommitted move is visible) and returns a
   `new_path -> old_path` map; `_ruff_new_findings` now falls back to the
   file's content at its OLD path when the new path has no baseline. Confirmed
   in a scratch repo first (`git show HEAD:pkg/mod.py` fails but
   `git diff --name-status -M HEAD` reports `R100 mod.py pkg/mod.py`).
2. **A new re-export `__init__.py` legitimately trips F401.** `rag_agent/__init__.py`
   is brand-new (no baseline, not a rename), and if it re-exports the class
   (`from rag_agent.rag_research_chatbot import RAGResearchChatbot`) ruff flags
   F401 "imported but unused" — even though re-exporting is the file's whole
   purpose. **Fixed** by adding `--per-file-ignores __init__.py:F401` to
   self_check's ruff invocation (both the json path and the opaque fallback).
   Scoped to F401 in `__init__.py` only — the single most conventional line in
   Python packaging — so syntax errors and other pyflakes issues there are
   still caught.

**Why this kept recurring:** each round fixed the *class* of "self_check gates
on something unrelated to the change" but the move-a-module goal keeps
surfacing new instances — whole-worktree scope (round 3), debt in a
touched-but-not-moved file (round 4), debt in a moved file and a re-export
`__init__.py` (this round). With rename-awareness and the `__init__.py`
convention handled, the differential now covers every file category a move
produces: modified-in-place (baseline at same path), moved (baseline at old
path), and genuinely-new (no baseline, must be clean — except the F401
`__init__.py` convention).

**Verified:** two new engine tests —
`test_self_check_forgives_lint_debt_in_a_moved_file` (ships `legacy.py` with an
unused import, has the maker relocate it verbatim into `pkg/`, asserts the run
finishes `done`) and `test_self_check_allows_reexport_init_py` (maker adds a
re-exporting `pkg/__init__.py`, asserts `done`) — plus a worktree unit test
`test_renamed_paths_detects_a_move`. The round-4
`test_self_check_fails_on_newly_introduced_finding` still passes, confirming
the gate still blocks genuinely new debt. Full suite: 58/58 pass. Ruff clean
(`--select E9,F` and default). **Not yet verified:** a sixth live run — but
every file category the POC produces is now exercised by a test against real
ruff/git subprocesses, and the two gaps were each reproduced deterministically
before fixing.

---

## Phase 1 follow-up — self_check was linting the frozen BDD harness ✅

Sixth live run. The rename + `__init__.py` fixes worked — none of
`rag_research_chatbot.py`'s pre-existing debt was flagged this time. The move
**actually completed** (confirmed on disk: `rag_agent/rag_research_chatbot.py`
present, `rag_agent/__init__.py` empty, root file gone), yet the run still
escalated on a *single* self_check finding:

```
features/steps/test_move_rag_research_chatbot.py:5:8 F401 `pytest` imported but unused
```

That file is the **step-definitions module author_bdd generated** — and it
routinely writes an unused `import pytest` into it. self_check already
excluded the feature directory from its *pytest* run (via `--ignore`), but
never from its *ruff* pass: the step-defs file was a changed (new) file, so it
landed in the differential's `changed` list and its F401 counted as
introduced. But that harness is author_bdd's frozen definition-of-done, not
the maker's implementation change — `bdd_gate` is what runs it. self_check has
no business linting it.

**Fixed:** self_check now drops any changed file living under a feature
directory (derived from `state["feature_paths"]`) — as well as the agent's own
package — before running ruff, via a new `_is_under_any()` path-prefix check.
This is the ruff-side equivalent of the pytest `--ignore` that was already
there. So self_check lints only the maker's actual implementation files;
`bdd_gate` remains the sole gate on the BDD harness.

**Why the maker still "stopped due to max iterations":** it wasn't actually
stuck — the diff and on-disk state show the move fully done (import in app.py
updated, package created, root file deleted). The maker just didn't emit an
explicit "done" before its 20-call budget; the graph proceeds to self_check
regardless, so this alone wouldn't have blocked finalization. The self_check
F401 was the real blocker.

**Verified:** new engine test `test_self_check_ignores_lint_in_bdd_harness`
(maker implements the kata and drops a new `features/steps/extra_helper.py`
with an unused `import pytest`; asserts the run finishes `done`). Full suite:
59/59 pass. Ruff clean. With this, every self_check false-positive the RAG POC
surfaced across rounds 3–6 is closed: unrelated-file debt, touched-file debt,
moved-file debt, re-export `__init__.py`, and now the generated BDD harness.
The move completing on disk means the next run should reach `bdd_gate` and
finalize `done` — the first end-to-end live success, if the scenarios pass.

---

## Phase 2 — Rails & memory ✅

Phase 1 (plus the six follow-up rounds) got the loop running end-to-end and
green on a real goal. Phase 2 is the "don't run forever, and learn between
attempts" layer from CODING_ENGINEER.md §3.4 / §6: real failure signatures,
no-progress detection, an LLM-classified diagnose, and durable pause/resume.

**Delivered:**

1. **`coding_agent/signatures.py`** — the §3.4 recipe as code:
   `sha1(phase | normalised_test_name | error_class | message_template |
   top_frame_func)`. `normalise_test_name` drops the parametrisation suffix
   (`test_add[3-5]` -> `test_add`); `template_message` strips the things that
   churn between edits (paths, line numbers, hex, durations, timestamps) but
   deliberately keeps assertion *values* so `expected 3 got 5` and
   `expected 4 got 6` stay distinct; `extract_failures` pulls the signable
   fields out of a pytest-json-report. 10 unit tests pin the "stable across
   churn, distinct across real differences" contract.
2. **Gates capture failing tests.** `self_check`/`bdd_gate` now store a
   normalised `failures` list (and self_check a `ruff_codes` list) alongside
   the summary, so diagnose can sign the actual failure rather than a
   stringified summary.
3. **LLM-classified diagnose.** New `DiagnosisResult` schema (category ∈
   syntax|test-logic|env|flake|design + a one-line insight), `_llm_diagnose`
   boundary via `invoke_structured`, and `DIAGNOSE_PROMPT`. The call degrades
   gracefully — any model/network error falls back to an `unknown` category
   and the code-only summary, so a diagnose hiccup never crashes the loop.
4. **`diagnose_node` rewrite** implementing the §3.4 hard exits in order:
   stop flag; **same signature twice in a row → active plan exhausted** (with
   a single plan, that escalates as `no_progress`; the machinery to route to a
   fresh plan and only escalate on the *second* consecutive exhaustion is in
   place for Phase 3); then the budget checks. A `flake` classification buys a
   bounded number of free retries (`_MAX_FLAKE_FREE_RETRIES = 2`) that don't
   burn an attempt — but never for a no-progress repeat, since an identical
   failure twice isn't flakiness. Routing is pure code: diagnose records
   `diagnosis.action` (retry | new_plan | escalate) and `_route_after_diagnose`
   reads it.
5. **Report** surfaces each lesson's category and short signature, and calls
   out a no-progress stall explicitly when the last two signatures match.
6. **State schema** gained `failure_signature`, `prev_failure_signature`,
   `exhausted_plan_ids`, `flake_free_retries`, `diagnosis`, and a `category`
   on each `Lesson`.

**Verified (all against real ruff/pytest/git subprocesses; the three LLM
boundaries mocked):**
- `test_no_progress_escalates_on_identical_failure` — a stuck maker producing
  the identical BDD failure escalates as `no_progress` after just 2 attempts,
  well inside a generous budget, and both lessons share a signature.
- `test_exhausts_budget_when_failures_keep_changing` — when each attempt fails
  *differently* (distinct signatures, so no-progress never trips) the attempt
  budget is the backstop; all signatures distinct.
- `test_flake_gets_a_free_retry` — a `flake` classification retries without
  incrementing `total_attempts`.
- `test_author_bdd_pauses_and_resumes_when_hitl_on_and_ambiguous`,
  `..._does_not_pause_on_clear_goal_with_hitl_on`,
  `..._does_not_pause_when_hitl_off_even_if_ambiguous` — the HITL flag gates
  the interrupt exactly as speced: pause only when the flag is on *and* the
  draft is ambiguous; resume continues to `done`.
- `test_killed_run_resumes_from_sqlite_checkpoint` — a run paused at the
  approval interrupt is resumed to completion by a **fresh graph instance on a
  new sqlite connection** over the same db + thread_id (stands in for a
  restarted process).
- 10 new `test_signatures.py` unit tests; the Phase 1 `test_retry_then_pass` /
  budget test updated for the new signed-lesson shape and no-progress
  behaviour.

Full `coding_agent` suite: **75 pass** (24 engine + 51 unit), ruff clean
(`--select E9,F` and default). Detecting the interrupt under `.invoke()` (vs
`.stream()`) turned out to need `graph.get_state(cfg).next` + task interrupts
rather than a `__interrupt__` return key — confirmed against the pinned
langgraph 0.3.34 before writing the tests.

**Deferred to Phase 3 (per §6):** ToT/GoT plan proposal + judging (Phase 2
still uses the single fixed `plan-1`, so the "two consecutive plans exhausted"
exit and plan-switch routing exist but can't fire yet), the adversarial
reviewer + review-rejection signatures, and cross-plan lesson aggregation.

**Not yet verified:** a live Ollama run exercising the real `_llm_diagnose`
classification and the actual interrupt in the Streamlit panel — the sandbox
has no model, so as with every prior round the LLM-facing prompt itself is the
one thing left to sanity-check live.

---

## What's next — Phase 3

Per `CODING_ENGINEER.md` §6 / §3.6: the "intelligence" layer that the Phase 2
rails were built to support.

- **ToT/GoT planning** in `plan_tot`: the primary model proposes several
  candidate plans, the secondary model judges/scores them, and the loop works
  the best one — replacing today's single fixed `plan-1`. This is what finally
  exercises the plan-switching path already wired into diagnose: on a
  no-progress plan exhaustion, route to `plan_tot` for a fresh plan built on
  the aggregated lessons, and only escalate on the **second** consecutive
  exhaustion (§3.4 exit 2).
- **Adversarial reviewer** (secondary model) after `bdd_gate` passes: an
  independent maker/checker separation that can `reject` on blocker/major
  findings. Review rejections get signed too — `review_signature(location,
  severity)` already exists in `signatures.py` — so a maker/checker stalemate
  is caught by the same no-progress rule (§3.4 exit 3).
- **Cross-plan lesson aggregation** (GoT): carry distilled lessons across plan
  switches so a new plan doesn't repeat a dead end.

Phase 4 then is the UI/observability polish (§5): budgets expander, diff
viewer, demo queries, telemetry wiring, and the worktree-cleanup decision
still open from the Phase 1 follow-ups.
