# What an eval harness found in my coding agent

**TL;DR** — I built an autonomous coding agent, then built an execution-based eval
harness to measure it. The harness found five defects. The first three were in the
*harness itself*, and every one of them reported a perfectly good agent run as a
failure. This is a write-up of how each was found and what it cost.

The agent is a LangGraph state machine that takes a goal and a git repo, works in an
isolated worktree, and iterates code → test → review until the tests pass or it
gives up and says why. Code: [`coding_agent/`](coding_agent/). Harness:
[`evals/`](evals/).

---

## Why execution-based, and not LLM-as-judge

The harness scores a run by executing hidden unit tests against the code the agent
actually produced. The verification tests are written into the worktree **only after
the agent has finished and committed** — so the agent cannot write assertions that
match its own implementation, which is the failure mode of letting a model grade
itself.

Two metrics, reported separately on purpose:

| Metric | What it actually measures |
|---|---|
| **Pass@1** | mostly the underlying model |
| **Recovery rate** | the graph built around it — conditional routing, and whether failure signatures fed back into state actually help the next attempt |

Conflating them tells you nothing about your own engineering. A better model raises
Pass@1 whatever the graph looks like.

The dataset (8 tasks: bugfix / feature / refactor × easy / medium / hard) is checked
in both directions, neither needing an LLM:

```bash
python -m evals.runner --validate   # hidden tests must FAIL on every unfixed seed
python -m evals.runner --selftest   # hidden tests must PASS on every reference solution
```

`--validate` earned its keep on the first run: `refac-002` passed on its own unfixed
seed. Behaviour-preservation tests cannot detect a refactor that by definition
preserves behaviour. It now carries structural assertions — a private helper must
exist and be called by both public functions — alongside the behavioural ones.

---

## The three harness bugs

Each of these produced the same symptom: **every task scored FAIL regardless of how
well the agent performed.** A false FAIL is worse than no eval at all, because it
sends you debugging the wrong system.

### 1. Verification ran against the seed, not the agent's output

`verify()` ran the hidden tests in `target_dir`. The agent never writes there —
`create_worktree()` puts each run in `<loop_state_dir>/worktrees/<run_id>` on branch
`coding-engineer/<run_id>`, and that branch is never merged back. So verification was
scoring the pristine seed, which fails by construction. That is precisely what
`--validate` asserts about every seed.

**How it was proven:** a stubbed agent that writes each task's *reference solution*
into a worktree created the same way the real one is. Before the fix, a provably
perfect run scored FAIL. After, `bug-001`, `feat-002` and `refac-002` all scored
`solved=True`.

That technique — construct a run you know is correct, assert the harness agrees —
is the only way to test a test harness. It also surfaced a second problem: the
worktree lives outside the temp workspace, so `rmtree` never reclaimed it, and
`create_worktree()` raises when the directory already exists. Orphans from one run
could break later ones.

### 2. A bare `python` in the verify command

The `bug-001` run reported `No module named pytest`, so the hidden tests never ran.
The dataset's verify command started with a bare `python`, which resolves through
`PATH` — on Windows under `uv`, that picked the uv-managed CPython rather than the
project venv.

`verify()` now substitutes `sys.executable` for a leading `python`/`python3`/`py`, so
verification always runs under the same interpreter as the harness — the one that
necessarily has pytest, since it is running this module.

**How it was proven:** shadowed `python` on `PATH` with a stub that exits 1 with
exactly that error, then confirmed the reference solution still scored `solved=True`.

### 3. The agent's own test gate had nothing to collect

This one is the most interesting, because the harness bug was *teaching the agent to
do the wrong thing*.

Two tasks escalated without ever writing the source file — `src/retry.py` and
`src/textutil.py` are absent from both runs' changed-file lists. The seed repos
contain no `tests/` directory, because acceptance tests are hidden by design.
`self_check` excludes the BDD directories, since those are `bdd_gate`'s job. So it
had nothing at all to collect: zero tests, pytest exit code 5, **reported as
passed**.

The agent was being told its implementation was fine while the module was still a
stub. The only gate that ever failed was its own BDD harness — so that is where it
spent its entire budget.

The fix seeds a deliberately shallow smoke test that asserts the required symbol
exists and is callable. It leaks no acceptance criteria — the goal text already names
the symbol — but it makes `testpaths=tests` resolve, so `self_check` runs something
real.

**The general lesson:** a gate that cannot fail is not a gate. Exit code 5 means
*zero tests collected*, and treating it as success is a vacuous pass. That distinction
later became an explicit flag in the agent itself, since zero-collected is legitimately
a pass in BDD mode and a failure in pytest mode.

---

## The two agent bugs

With the harness trustworthy, its failures became real signal.

### 4. Every non-lint failure reported as a lint failure

A run escalated with `two_plans_exhausted` after `diagnose` told the agent three
times to fix ruff — while ruff had exited 0 and `ruff_codes` was empty.

The real failure was a pytest **collection** `ImportError`: the function under test
did not exist. `_signature_and_detail` treated "no structured pytest failures" as
"therefore ruff", but a collection error exits 2 with an empty `failures` list,
because a collection error is not a test failure. Such a run fell into the ruff
branch, where the detail handed to the diagnosing model was the literal string
`"ruff findings: "` with nothing after it.

The model was reasoning correctly about an empty report.

Worse, that branch signed the failure with a **constant** signature —
`compute_signature(phase, "ruff", "ruff", "", "")` — regardless of the actual error.
Two collection errors in a row therefore tripped the "same signature twice"
no-progress rule and exhausted the plan immediately. That is why three attempts were
burned without ever reaching the source file.

The branch now decides in order: structured pytest failures → ruff *only* when ruff
actually failed → a pytest non-zero exit with no structured failures, signed on the
message template and labelled explicitly as not a lint failure → an honest "neither
tool produced a diagnosable result", rather than blaming a passing tool.

Regression tests use that run's actual `state.json` as the fixture.

**The general lesson:** a fallback branch that guesses is worse than one that admits
ignorance, because a confident wrong diagnosis is fed straight to a model that will
act on it. And a failure signature that collapses distinct errors into one value will
silently poison any no-progress heuristic built on top of it.

### 5. No output ceiling on either provider

The first live run against a real folder: the goal was "write a hello world FastAPI
app". A single `author_bdd` call produced **84,372 completion tokens in 675 seconds**
— eleven minutes on one request, for a hello-world spec, consuming most of the run's
wall-clock budget before any code was written.

Neither provider was constructed with a limit, so the model generated until the
server's own cap. There is now a per-call ceiling on both (`max_tokens` for
OpenAI-compatible, `num_predict` for Ollama), defaulting to 8192 — roughly ten times
the largest legitimate output observed — so runaways stop without truncating real
work, and a truncated response fails fast into the structured-output retry rather
than stalling.

---

## What I'd do differently

- **Validate the harness before trusting a single number.** Three of five defects
  were in the measuring instrument. The `--validate` / `--selftest` pair should have
  existed before the first scored run, not after.
- **A stubbed perfect agent is the cheapest test you can write.** It costs no
  inference, runs in seconds, and catches the class of bug where the harness is
  scoring the wrong directory entirely.
- **Every gate needs a proof that it can fail.** Both the vacuous `self_check` and the
  refactor task that passed on its own unfixed seed are the same bug wearing
  different clothes.
- **Budget ceilings belong in the client, not in the prompt.** An unbounded call is an
  unbounded outage.

---

## A note on how this was built

Most of this code was written with an AI coding assistant, and the commit history says
so. I think that is the interesting part rather than something to hide.

What did not come from the assistant was the judgment: deciding that a failing BDD fix
should be reverted rather than patched further when it started looping; refusing to
let a bug in `diagnose` be parked as a test-harness quirk, because a wrong diagnosis
fed to a model makes the agent unusable in production; insisting a fix land on a clean
branch off `main` rather than on top of an abandoned one; and reading a climbing token
count as the real cause of an eleven-minute stall.

Each of those was a call the assistant got wrong first, and each was the difference
between a run that looked fine and a system that actually worked. Building agents with
AI assistance does not remove the need to know what correct looks like. It raises the
cost of not knowing, because the wrong answer arrives fluent, fast, and with a
plausible explanation attached.
