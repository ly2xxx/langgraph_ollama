# Coding Engineer API

A FastAPI wrapper so you can point the agent at any local folder from Swagger,
rather than editing a CLI command or a Streamlit form.

```bash
uv sync --extra api
uv run uvicorn api.main:app --reload --port 8009
# open http://127.0.0.1:8009/docs
```

## The flow in Swagger

| # | Call | Why |
|---|---|---|
| 1 | `GET /folders/roots` | starting points — cwd, home, and on Windows every real drive |
| 2 | `GET /folders?path=…` | walk to the repo; each entry shows `is_git_repo`, so you can see where to stop |
| 3 | `GET /models` | confirm which primary/secondary models a run would use *before* spending ten minutes |
| 4 | `POST /runs` | paste the `path` from step 2 plus a goal → `202` and a `run_id` |
| 5 | `GET /runs/{id}` | poll: status, the per-node trace, changed files, branch, worktree |
| 6 | `GET /runs/{id}/report` · `GET /runs/{id}/diff` | the run report and the diff once it finishes |

## `test_style`: bdd or pytest

`POST /runs` takes `test_style`, and it matters more than it looks.

**`bdd`** (default) — the original loop. `author_bdd` writes a Gherkin feature file
*plus* a pytest-bdd step-definitions module, freezes them, and `bdd_gate` runs them.

**`pytest`** — skips `author_bdd` and `bdd_gate` entirely. Intake's acceptance
criteria become the definition of done, the agent writes plain pytest tests
alongside the implementation, and `self_check` is the gate.

Use `pytest` when the model cannot produce the BDD artefact reliably. Asking for a
whole feature file and a step-definitions module as escaped JSON strings in one
structured call is the largest and most brittle request in the loop: with
`glm-5.3:cloud` it produced 84k completion tokens in a single 675-second call, and
under an 8192-token cap it truncated mid-JSON on every retry — the run never got
past authoring. `pytest` mode removes that call from the graph.

In `pytest` mode `self_check` is the only test gate, so **zero collected tests is a
failure** rather than the pass it correctly is in `bdd` mode (where the only tests
in scope are the frozen scenarios that `bdd_gate` owns). Without that, a run could
finalize having proved nothing.

## Things the API tells you up front

- **`POST /runs` rejects a target that is not inside a git repo** (400). The agent
  branches a worktree off HEAD; without a repo it silently falls back to copying,
  which makes the result hard to review. Better to hear that in a second than after
  a long run.
- **`GET /folders` lists `uncommitted` paths.** The worktree is cut from HEAD, so
  uncommitted work is *invisible to the agent* — the most common surprise with this
  tool. Commit first if you want it seen.
- **Your working tree is never edited.** Changes land on `coding-engineer/<run_id>`
  in a worktree under `.loop/worktrees/`, which `GET /runs/{id}` reports so you can
  diff and merge yourself.
- **`.loop/` lands beside your target repo, not beside this server.** Point a run at
  `H:/code/sandbox/proj1` and its worktrees, reports and checkpoints go to
  `H:/code/sandbox/.loop/` — next to the repo you are working on, not wherever
  `uvicorn` happened to be started from. See [Where run output lands](#where-run-output-lands).

## One run at a time

A second `POST /runs` while one is active returns **409**. This is deliberate rather
than a missing feature: per-run model overrides are applied through environment
variables (`get_llm` reads env at call time, as the Streamlit panel does), and the
environment is process-global — two concurrent runs with different overrides would
silently read each other's models.

## Stopping

`POST /runs/{id}/stop` raises the engine's stop flag. The loop checks it between
attempts, so the run ends at the next checkpoint — it is not killed mid-write, and
the worktree is left consistent. Status goes `running → stopping → escalated`.

## Where run output lands

Everything a run produces lives under a single `.loop/` directory, placed **beside the
git repo root of the target you pointed it at**:

```
H:/code/sandbox/                     <- the target repo's parent
├── proj1/                           <- "target_dir": "H:/code/sandbox/proj1"
└── .loop/
    ├── worktrees/<run_id>/          <- branch coding-engineer/<run_id>, where the agent writes
    └── state/coding-engineer/
        ├── checkpoints.db           <- SqliteSaver; a killed run resumes from here
        └── <run_id>/
            ├── run-report.md        <- GET /runs/{id}/report
            ├── state.json
            └── STOP                 <- POST /runs/{id}/stop
```

Beside the repo rather than inside it, because a worktree nested in its own repo
confuses git, and `self_check`/`bdd_gate` would otherwise collect tests out of every
past run's worktree.

If the target is a subdirectory of a repo, `.loop/` still anchors on the **repo root's**
parent — the subdirectory's own parent is still inside the repo. For a non-git target
(rejected by `POST /runs`, but reachable from the CLI) it anchors on the target itself.

`CODING_AGENT_LOOP_DIR` overrides all of this with one fixed location, which is what
the test suite uses.

> Runs from before this change wrote to `.loop/` relative to whatever directory the
> server or CLI was launched from. Those reports are still on disk, but
> `GET /runs/{id}/report` will not find them — move the old `.loop/` beside the target,
> or point `CODING_AGENT_LOOP_DIR` at it.

## Seeing what the agent is doing

Every LLM and tool call prints to the console (stderr), on **both** providers:

```
  [llm→] primary   ollama/glm-5.2:cloud @ http://localhost:11434  6 msg, 4.2k chars
  [llm←] primary   3.6s  1572→249 tok  finish=stop  1 tool call(s)
         → write_file({'path': 'main.py', 'content': 'from fastapi import FastAPI…'})
  [tool→] write_file  path=main.py content=from fastapi import FastAPI…
  [tool←] write_file  0.0s  wrote main.py
```

Four fields there were invisible before, each of which cost a debugging round:

| | |
|---|---|
| `provider/model @ base_url` | which transport actually served the call — the native Ollama route has no gateway UI at all |
| `finish=length` | the response was **truncated**; it is flagged loudly, and it is absent from LiteLLM's logs |
| `no tool calls` | a model emitting a tool call as *prose* shows up here as zero calls while its text looks like one |
| tokens + duration | runaway generations, per call |

`CODING_AGENT_LOG_LLM=0` turns it off; `=2` also previews prompt and response text.

To exercise the native Ollama transport (no gateway), set these before starting
uvicorn — `POST /runs` overrides the model but not the provider:

```
CODING_AGENT_PRIMARY_PROVIDER=ollama
CODING_AGENT_PRIMARY_BASE_URL=http://localhost:11434
CODING_AGENT_SECONDARY_PROVIDER=ollama
CODING_AGENT_SECONDARY_BASE_URL=http://localhost:11434
```

## Configuration

| Env var | Default | |
|---|---|---|
| `CODING_ENGINEER_API_HOST` | `127.0.0.1` | localhost by default, on purpose — see below |
| `CODING_ENGINEER_API_PORT` | `8009` | |
| `CODING_ENGINEER_API_ROOTS` | *unset* | `os.pathsep`-separated allow-list of targetable directories |
| `CODING_ENGINEER_API_MAX_RUNS` | `50` | finished runs kept in memory |

Model and gateway settings come from the agent's own env (`.env`, `CODING_AGENT_*`,
`OPENAI_BASE_URL`, …) exactly as the CLI and Streamlit paths use them.

## Security

**This endpoint runs an LLM-driven agent that writes files and executes commands on
a folder you name.** With `CODING_ENGINEER_API_ROOTS` unset, that is any folder the
process can reach — which is what makes picking an arbitrary repo convenient, and is
only reasonable while the server is bound to localhost with no auth.

Before exposing it to anything wider: set `CODING_ENGINEER_API_ROOTS`, put real
authentication in front, and reconsider whether it should be reachable at all.

## Layout

| File | |
|---|---|
| `main.py` | the app and its routes |
| `schemas.py` | request/response models — the descriptions are the Swagger help text |
| `runner.py` | background execution and the in-memory run registry |
| `folders.py` | folder browsing, path validation, git checks |
| `settings.py` | environment configuration |

`coding_agent/` imports nothing from here, and `runner.py` imports the engine lazily
inside functions — so the agent stays importable and testable without FastAPI, and
the API is testable without the LLM stack.
