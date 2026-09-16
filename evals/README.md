# Execution-based evaluation harness

Measures what the Coding Engineer agent *achieves*, not what a model says about it.

## Why this exists

The common answer to "how do you evaluate your agent?" is LLM-as-a-judge. It is
subjective, it drifts, and it is circular when the judge and the agent share a
model family. This harness scores the agent by **running hidden unit tests against
the code it actually produced**, in an isolated workspace.

The tests are written into the worktree *after* the agent has finished. The agent
never sees the assertions it is scored on, so it cannot pass by writing tests that
match its own implementation.

## Metrics

| Metric | Definition | What it isolates |
|---|---|---|
| **Pass@1** | Solved on the first attempt, no correction loop | Raw model capability |
| **Solve rate** | Solved at any point within budget | End-to-end usefulness |
| **Recovery rate** | Of tasks that failed attempt 1, the share later solved | **The harness itself** — conditional routing and failure-signature feedback |
| **Escalation rate** | Hit a budget and exited gracefully | Loop-termination guardrail working |
| **Mean attempts/solve** | Cost of a success | Token/time efficiency |

Recovery rate is the one that matters. Pass@1 mostly measures the underlying model;
recovery rate measures the graph you built around it. A higher recovery rate at an
unchanged Pass@1 is direct evidence the harness adds value.

## Dataset integrity

A benchmark nobody validated is a number nobody should trust. Two checks, both
runnable without an LLM:

```bash
python -m evals.runner --validate   # hidden tests must FAIL on every unfixed seed
python -m evals.runner --selftest   # hidden tests must PASS on every reference solution
```

Both must be green. `--validate` catches tasks that are no-ops; `--selftest` catches
tasks that are impossible. The first run of `--validate` caught a real defect: the
`refac-002` refactor task passed on its own seed, because behaviour-preservation
tests cannot detect a refactor. It now carries structural assertions (a private
helper must exist *and* be called by both public functions) alongside the
behavioural ones.

## Running

```bash
python -m evals.runner                          # full run
python -m evals.runner --tasks bug-003 feat-003 # subset
python -m evals.runner --out results.json       # machine-readable report
python -m evals.runner --keep                   # keep workspaces to inspect diffs
```

8 tasks across bugfix / feature / refactor at easy / medium / hard.

## Interview notes

**"How do you evaluate agents?"**
Execution-based trajectory evals. Fixed benchmark, isolated git worktree per task,
hidden tests applied post-hoc, deterministic pass/fail. I report Pass@1 and recovery
rate separately so model capability and harness value don't get conflated.

**"How do you know the benchmark is any good?"**
Every task is checked in both directions — the hidden tests must fail on the unfixed
seed and pass on a reference solution. That caught a dead task on the first run.

**"What does the harness actually add?"**
Recovery rate. When attempt 1 fails, stdout from the failing test run is written into
the graph state as a failure signature, and a conditional edge routes back to the
coding node with that context. Recovery rate is the measured value of that edge.

**"How do you stop it looping forever?"**
Budgets in state: `max_attempts_per_plan`, `max_plans`, `max_total_attempts`,
`wall_clock_s`, `token_budget`. On exhaustion it exits through a graceful escalation
node returning partial artifacts, rather than burning tokens. Escalation rate is
tracked so the guardrail is visible, not silent.
