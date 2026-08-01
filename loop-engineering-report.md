# Loop Engineering — Comprehensive Report

> **Sources**
> - [libraries.io/pypi/loop-mcp](https://libraries.io/pypi/loop-mcp) — package metadata
> - [Addy Osmani — *Loop Engineering*](https://addyosmani.com/blog/loop-engineering/) (Jun 2026) — canonical essay
> - [O'Reilly Radar repost](https://www.oreilly.com/radar/loop-engineering/) (Jun 22, 2026)
> - [Lushbinary — *The Guide for AI Agents*](https://lushbinary.com/blog/loop-engineering-ai-coding-agents-guide/) (Jun 9, 2026)
> - [Requesty — *How to Build AI Agent Loops That Run Themselves*](https://www.requesty.ai/blog/loop-engineering-how-to-build-ai-agent-loops-that-run-themselves) (Jun 17, 2026)
> - [Loop-Engineering on GitHub](https://github.com/arjun988/Loop-Engineering) — reference MCP server (`loop-mcp`)
> - [Peter Steinberger tweet](https://x.com/steipete/status/2063697162748260627) — "design loops, not prompts"
> - [Boris Cherny (Anthropic, Claude Code)](https://x.com/rohanpaul_ai/status/2063289804708835412) — "I don't prompt Claude anymore, I have loops running"
>
> *Compiled 2026-07-23 by Helpful Bob for Master Yang.*

---

## 1. Executive Summary

**Loop engineering** is the practice of designing the *system around* an AI agent so that it works iteratively toward a goal without being prompted step-by-step by a human. Where prompt engineering optimises the words sent to a model, loop engineering optimises the **control system** that drives the model: triggers, feedback, verification, state, and stop rules.

The idea has crystallised in mid-2026 around three converging signals:

1. **Models handle long tasks.** METR benchmarks show Claude Opus 4.6 completing 50% of tasks that take ~12 hours (vs. Opus 4's 1h40m a year earlier). The capability ceiling moved ~6×.
2. **Loops are built into the tools.** Claude Code ships `/loop`, scheduled tasks, hooks, and sub-agents. OpenAI Codex ships an **Automations** tab with cron, worktree isolation, and a Triage inbox. The infrastructure that used to be custom bash now ships in the product.
3. **A leadership quote pattern.** Peter Steinberger (Steipete): *"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents."* Boris Cherny (head of Claude Code at Anthropic): *"I don't prompt Claude anymore. I have loops running that prompt Claude and figuring out what to do. My job is to write loops."*

`loop-mcp` (v0.4.0 on PyPI) is a reference MCP server — a working code example of the framework. It's not the framework itself; it is one implementation that maps the five canonical primitives to a runnable, scheduled, verified control loop. Think of it as: **GitHub Actions + AI Agents + an intelligent, self-verifying control loop**.

---

## 2. Definition

> **Loop engineering** is the practice of designing the system around an AI agent so it can work iteratively toward a goal instead of being manually prompted one step at a time. The engineer focuses on the goal, feedback checks, retry logic, state, and stopping rules — rather than the prompt itself.

### How it differs from related concepts

| Concept | One-line definition | Scope |
|---|---|---|
| **Prompt engineering** | Craft the best text to send the model. | One turn. |
| **Context engineering** | Curate what the model sees (memory, tools, files). | One run. |
| **Agent harness engineering** | Build the environment one agent runs inside. | One agent. |
| **Agentic engineering** | Build AI systems that can act with some autonomy. | Any agent architecture. |
| **Loop engineering** | Design the **control loop** that keeps the agent working until success. | A scheduled, verified, bounded cycle. |
| **Factory model** | The system that *builds* the software — the loop is one floor above the harness. | A whole engineering organisation. |

A useful framing from Addy Osmani:

> "Loop engineering: build the **control loop** that keeps the agent working until success."
> "Agentic engineering: build an **agent** that can do work."

A loop is a recursive goal: you define a purpose and the AI iterates until complete.

---

## 3. The Canonical Framework — Five Primitives + Memory

The framework has six parts. The first five are the moving parts; the sixth is what makes it durable.

| # | Primitive | Job in the loop |
|---|---|---|
| 1 | **Automations** | The heartbeat — discovery + triage on a schedule. |
| 2 | **Worktrees** | Isolated checkouts so parallel agents don't collide. |
| 3 | **Skills** | Codified project knowledge read every run. |
| 4 | **Plugins / connectors** | MCP-based access to the tools you already use. |
| 5 | **Sub-agents** | Maker / checker separation — the one who writes is not the one who grades. |
| 6 | **State / Memory** | On-disk history of what's done, what's tried, what's next. The agent forgets; the repo doesn't. |

Both flagship products implement all six today. The names differ; the capability is the same:

| Primitive | OpenAI Codex | Claude Code |
|---|---|---|
| Automations | **Automations** tab (project, prompt, cadence, environment) → Triage inbox; `/goal` for run-until-done | Scheduled tasks + cron, `/loop`, `/goal`, hooks, GitHub Actions |
| Worktrees | Built-in worktree per thread | `git worktree`, `--worktree` flag, `isolation: worktree` on a subagent |
| Skills | Agent Skills (SKILL.md); `$name` or implicit invocation | Agent Skills (SKILL.md) |
| Plugins / connectors | Connectors (MCP) + plugins for distribution | MCP servers + plugins |
| Sub-agents | `.codex/agents/*.toml` (name, description, model, reasoning effort) | `.claude/agents/*` + agent teams |
| State | Markdown / Linear via a connector | AGENTS.md, progress files, or Linear via MCP |

### 3.1 Automations — the heartbeat

Automations are what make a loop an *actual* loop and not just one run you did once. They go off on a schedule, do discovery and triage, and surface what needs human attention. In Codex they live in the Automations tab; in Claude Code they're scheduled tasks, `/loop`, cron, hooks, or GitHub Actions.

There's a second in-session primitive worth knowing: **`/goal`**. It keeps working across turns until a verifiable stopping condition holds, and after every turn a separate small model checks whether you're done. The agent that wrote the code isn't the one grading it. You can give it something like *"all tests in `test/auth` pass and lint is clean"* and walk away. Both Claude Code and Codex have a `/goal` primitive — same idea, different surface.

### 3.2 Worktrees — so parallel doesn't turn into chaos

The second you run more than one agent, the files start colliding. Two agents writing the same file is the exact same headache as two engineers committing to the same lines and not talking. A **git worktree** fixes it: a separate working directory on its own branch sharing the same repo history. One agent's edits literally cannot touch the other's checkout.

**Important caveat:** worktrees take away the mechanical collision, but **the human is still the ceiling**. Your review bandwidth decides how many you can actually run, not the tool. (This is what Osmani calls the **orchestration tax**.)

### 3.3 Skills — stop explaining your project every single time

A **skill** is a folder with a `SKILL.md` (instructions + metadata) plus optional scripts, references, and assets. Codex invokes with `$name` or `/skills`; Claude Code uses the same format. A tight, boring description beats a clever one — the model invokes the skill when its task matches the description.

Skills are also where **intent** stops costing you over and over. Without skills the loop re-derives your whole project from zero every cycle; with skills it compounds. A skill is **authoring format**; a **plugin** is how you ship it. When you want to share a skill across repos or bundle a few together, you package them as a plugin.

> Related concept: **intent debt** — the agent starts every session cold and will fill any hole in your intent with a confident guess. A skill is that intent written down on the outside.

### 3.4 Plugins and Connectors — the loop touches your real tools

A loop that can only see the filesystem is a tiny loop. **Connectors**, built on **MCP** (Model Context Protocol), let the agent read your issue tracker, query a database, hit a staging API, or drop a message in Slack. Codex and Claude Code both speak MCP, so a connector you wrote for one usually just works in the other.

Plugins bundle connectors + skills together so your teammate installs your setup in one go instead of rebuilding the whole thing from memory.

### 3.5 Sub-agents — keep the maker away from the checker

The most useful structural thing in a loop, by far, is splitting the one who writes from the one who checks. The model that wrote the code is way too nice grading its own homework. A second agent with different instructions (and sometimes a different model) catches the stuff the first one talked itself into.

The typical split: **one agent explores, one implements, one verifies against the spec.** You can use a strong model on high reasoning effort for the security reviewer and a fast read-only model for the file scanner. This is what `loop-mcp` calls the **maker/checker gate**: the agent makes changes; an independent checker decides whether the goal is met. The agent never grades its own homework.

Caveat: sub-agents burn more tokens since each does its own model and tool work. Spend them where a second opinion is worth paying for.

### 3.6 Memory / State — the spine of the loop

> "The model forgets everything between runs, so the memory has to be on disk and not in the context. The agent forgets; the repo doesn't." — Addy Osmani

A markdown file, a JSON state file, a Linear board, anything that lives outside the single conversation and holds what's done and what's next. The state file is the spine: it remembers what got tried, what passed, what is still open, so tomorrow's run picks up where today stopped. `loop-mcp` stores it in `.loop/state/<loop-name>.json` with run history, attempts, lessons, and budgets.

---

## 4. The Anatomy of a Run (per the `loop-mcp` reference)

The `loop-mcp` server maps all six primitives to a concrete control loop. The lifecycle of a single run:

```
run_loop_now ──► brief (goal, working dir, stop rule)
                │
                ▼
   agent makes the smallest change
                │
                ▼
complete_loop_run ──► maker self-check ──► independent checker gate
                │          │                    │
                │          │            ┌───────┴───────┐
                │          │        goal met?       not yet
                │          │            │                │
                ▼          ▼            ▼                ▼
         open PR & stop   open PR   attempts left? ──yes──► iterate
                          & stop                       (same run_id)
                              │
                              ▼
                       no / repeated failure
                              │
                              ▼
                     escalate to human
```

### Two gates, not one

A `loop-mcp` loop has **two** verification commands:

```json
{
  "verification_command": "npm test",                              // maker's fast self-check
  "goal_check_command": "npm run test:integration && npm run lint" // independent objective gate
}
```

A PR is opened **only when both pass**. This is the maker/checker pattern enforced at config time.

### Safety rules that separate a real loop from a cron job

```json
{
  "max_attempts": 3,        // escalate to a human after 3 failed attempts
  "max_runs_per_day": 24,   // daily run cap (heartbeat budget)
  "cost_budget": 5.00,      // cumulative USD token-cost ceiling (0 = unlimited)
  "isolation": "worktree"   // "worktree" (parallel-safe) or "branch"
}
```

The loop also performs **no-progress detection**: if the same failure occurs twice in a row it escalates immediately rather than burning tokens on a dead end. This is the explicit anti-pattern Osmani calls the **"Ralph-Wiggum runaway loop"** — an agent that just keeps going without recognising it has failed.

### 4-condition suitability test

Before you build a loop at all, `loop-mcp` runs a pre-flight check (via the `check_loop_suitability` tool). The four conditions are roughly:

1. **Is the work repetitive?** (Loops are for recurring, predictable work, not one-offs.)
2. **Is there a verifiable success condition?** (You need a check that says "done".)
3. **Are the side-effects reversible or low-risk?** (PRs that need review; never auto-merge to main.)
4. **Is the cost bounded?** (You can put a dollar cap on it.)

Good candidates: CI triage, dependency updates, lint/format fixes, doc sync, flaky test detection, security patches.

Bad candidates: architecture decisions, auth/payment code, production deployments, vague product work.

---

## 5. `loop-mcp` — The Reference Implementation

### 5.1 What it is

- **PyPI:** [`loop-mcp`](https://libraries.io/pypi/loop-mcp), currently **v0.4.0**
- **Author:** Codez ([@0xCodez](https://x.com/0xCodez))
- **License:** MIT
- **Stack:** Python MCP server; works with any MCP-aware agent (Cursor, Kiro, Claude Desktop, etc.)
- **Repo:** [github.com/arjun988/Loop-Engineering](https://github.com/arjun988/Loop-Engineering)
- **"Developed by: Anthropic"** claim in PyPI metadata is content from the package author, not verified by Anthropic — treat as community project.

### 5.2 Two ways to install

```bash
# Option 1 — uv (recommended, no separate install)
uvx loop-mcp

# Option 2 — pip
pip install loop-mcp
loop-mcp
```

### 5.3 Configure it in your AI agent

For **Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "loop-engineering": {
      "command": "uvx",
      "args": ["loop-mcp"]
    }
  }
}
```

For **Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, same uv/pip template).

### 5.4 The MCP tools the server exposes

| Tool | Purpose |
|---|---|
| `check_loop_suitability` | Run the 4-condition test before building a loop. |
| `create_loop` | Set up a new loop (checker gate, stop rules, budgets, isolation). |
| `start_loop` / `stop_loop` | Activate / pause the scheduler. |
| `run_loop_now` | Begin a run — returns the brief for the host agent to execute. |
| `complete_loop_run` | Submit an attempt (the loop body): runs the checker, opens a PR, iterates, or escalates. |
| `list_pending_runs` | Show runs the scheduler queued for the next agent session. |
| `run_verification` | Run a loop's verification command on demand. |
| `set_goal_check` | Set/update the independent checker gate. |
| `configure_verification` | Set/update the maker self-check command. |
| `list_loops` / `delete_loop` | Manage loop registry. |
| `add_skill` / `list_skills` | Manage reusable skill templates. |
| `view_state` | Check loop history, attempts, and metrics. |
| `add_lesson` | Record learnings for future runs. |
| `get_metrics` | See overall performance. |

### 5.5 Repository structure

```
loop-engineering/
├── python/                          # Python MCP server
│   ├── src/loop_engineering_mcp/
│   │   ├── server.py                # MCP server
│   │   ├── loop_manager.py          # Loop CRUD
│   │   ├── skill_manager.py         # Skill templates
│   │   ├── state_manager.py         # State tracking
│   │   ├── loop_executor.py         # Control loop: isolation, checker gate, stop rules
│   │   ├── scheduler.py             # Cron scheduler (the heartbeat)
│   │   ├── suitability.py           # 4-condition loop suitability test
│   │   ├── verification_runner.py   # Maker/checker gate runner
│   │   ├── github_client.py         # GitHub integration
│   │   └── worker.py                # Background worker
│   └── tests/
├── shared/skills/                   # Reusable skill templates
│   ├── ci-triage.md
│   ├── dependency-updates.md
│   └── lint-fixes.md
└── references/                      # Theory + how-to
    ├── README.md
    ├── FRAMEWORK.md
    └── QUICKSTART.md
```

### 5.6 Demo: a CI triage loop end-to-end

**User:** "Create a CI triage loop that runs every 6 hours."

**Agent:**
> ✅ Loop 'ci-triage' created!
>  Schedule: Every 6 hours
>  Verification: npm test
>  Goal: All CI failures classified
>
>  Files created:
>  - .loop/loops.json (configuration)
>  - .loop/skills/ci-triage.md (instructions)
>  - .loop/state/ci-triage.json (state tracking)

**User:** "Start it."

**Agent:**
> ✅ Loop started and will run automatically.

**User:** "What loops are running?"

**Agent:**
> 📊 Active loops:
>  ci-triage
>  - Last run: 2 hours ago
>  - PRs today: 3 (2 merged)
>  - Acceptance rate: 67%
>  - Token cost today: $4.20

**What the loop does unattended:**

- 🔍 Detects CI failures
- 🏷️ Classifies them (flake vs. bug vs. env issue)
- 🛠️ Drafts fixes for deterministic bugs
- 🧪 Runs tests
- 📬 Opens PRs
- 🚨 Escalates complex issues
- 📚 Records lessons learned

**The 4-condition CI triage example (Requesty's variant):**

```yaml
# Claude Code: .claude/commands/daily-pr-review.md
Schedule: Weekdays at 10:15am
Trigger: cron
Loop type: Cron loop (scheduled batch)
Sub-agents: enabled
Action:
  - Find all PRs older than 3 days
  - Spawn reviewer sub-agent per PR
  - Cross-check each PR against the diff + tests
  - Post actionable feedback as a PR comment
Stop condition: zero PRs older than 3 days, or max_iterations reached
```

---

## 6. The Four Loop Types (Requesty classification)

Every production loop fits one of four patterns:

| Type | When it runs | Use cases |
|---|---|---|
| **Heartbeat loop** | Continuously on a short interval (seconds to minutes) | Log monitoring, service health, drift detection |
| **Cron loop** | Scheduled at specific times | Daily code review, weekly dep audits, morning standup summaries |
| **Hook loop** | Triggered by external events (PR pushed, CI fails, Slack message) | Auto-triage on push, post-merge cleanup, alert routing |
| **Goal loop** | Iterates until a success condition is met, then stops | Refactors, bug hunts, migrations, large upgrades |

A single system often composes them: a cron loop opens a goal loop, which spawns a sub-agent, which fires a hook loop on a verification failure.

---

## 7. Cost Economics — Why Routing Matters

Agent loops are **token-intensive**. A daily PR review loop that spawns 5 sub-agents, each reading 50K tokens of context, costs real money at frontier pricing. The fix is to route each step to the right model tier:

| Loop step | Model tier | Cost per 1M tokens |
|---|---|---|
| File scanning and classification | Nano (GPT-5.4-nano, Gemini Flash) | $0.10 – $0.30 |
| Summarisation and drafting | Mid-tier (Sonnet 4.6, GPT-5.4) | $1 – $3 |
| Final review and decision | Frontier (Opus 4.8, GPT-5.5) | $10 – $15 |

Add **prompt caching** (90% reduction on repeated system prompts and tool definitions) and the math gets dramatic. A loop that would cost **$50/day** at frontier pricing drops to **$8 – $12/day** with routing and caching combined.

This is also why the framework is sceptical of naive frontier-only loops. Loop engineering is meaningless without budget caps and per-step model routing, otherwise it's just a credit card with a heartbeat.

---

## 8. Common Failure Modes

| Failure | Symptom | Mitigation |
|---|---|---|
| **Token runaway** | A goal loop with no `max_iterations` burns $500 in an hour. | Always set a ceiling; start with 50 iterations. |
| **Context rot** | Long-lived loops that keep appending to the same context window degrade in quality. | Sub-agents with fresh context per iteration, or compaction. |
| **Overconfident termination** | The agent declares "done" when it has only checked half the codebase. | Second agent verifier, or a hard condition (zero test failures, zero lint errors) rather than soft judgement. |
| **State amnesia** | The loop forgets what it already processed. | Write state to a file or DB after each iteration; on restart read the checkpoint. |
| **Ralph-Wiggum runaway** | No `max_attempts`, no no-progress detection, just keeps going. | Stop rules + repeated-failure detection + escalation. |
| **Cross-agent collisions** | Two loops edit the same file. | Always use worktree isolation. |
| **Toolchain failures mid-loop** | Provider goes down, loop crashes. | LLM gateway with failover + retries. |

---

## 9. What the Loop *Doesn't* Do For You — Osmani on "Stay the Engineer"

The loop changes the work; it does not delete you from it. Three problems actually get *sharper* as the loop gets better:

1. **Verification is still on you.** A loop running unattended is also a loop making mistakes unattended. Your job is to ship code you confirmed works.
2. **Comprehension debt grows faster.** The faster the loop ships code you didn't write, the bigger the gap between what exists and what you actually get. You have to *read* what the loop made.
3. **Cognitive surrender is the default.** When the loop runs itself it's tempting to stop having an opinion and just take whatever it gives back. Designing the loop is the cure when you do it with judgement; the accelerant when you do it to avoid thinking. Same action, opposite result.

> "Loops can result in different outcomes depending on you. Two people can build the exact same loop and get completely opposite results. One uses it to move faster on work they understand deeply. The other uses it to avoid understanding the work at all. The loop doesn't know the difference. You do."
> — Addy Osmani

The closing mantra of the framework: **"Build the loop. Stay the engineer."**

---

## 10. Related Concepts — The Loop's Neighbours

| Concept | Relationship to loop engineering |
|---|---|
| **Prompt engineering** | What the loop replaces as the primary leverage point. |
| **Context engineering** | Skill files are the loop's context-engineering substrate. |
| **Agent harness engineering** | One floor below the loop. Harness = the environment an agent runs inside; loop = the system that pokes the agent on a timer. |
| **Factory model** | One floor above. The factory is the system that *builds* the software; the loop is one of its cells. |
| **Ralph / Ralph Wiggum technique** | A specific implementation of an iterate-until-done loop. The `loop-mcp` docs reference "Ralph-Wiggum runaway loops" as the failure mode. |
| **Adversarial code review** | A sub-agent pattern — the checker is explicitly hostile to the maker's claim. |
| **Long-running agents** | Agents that survive across multiple sessions, depending on durable on-disk state (the loop's memory). |
| **Orchestration tax** | The human cost of reviewing loop output; worktrees remove the mechanical part, humans are still the ceiling. |
| **Intent debt** | The cost of explaining your project to the agent every session; skills are the loop's payment plan. |
| **Code agent orchestra** | Multi-agent composition pattern; the loop is the conductor. |

---

## 11. Implementation Patterns — Concrete Recipes

### 11.1 Cron-based daily PR reviewer (Claude Code)

```yaml
# .claude/commands/daily-pr-review.md
name: daily-pr-reviewer
schedule: "15 10 * * 1-5"     # 10:15 weekdays
loop_type: cron
sub_agents: [pr-classifier, pr-reviewer, pr-commenter]
verification: gh pr list --state open --json createdAt
goal_check: |
  count=$(gh pr list --state open --json createdAt | jq '[.[] | select((.createdAt | fromdateiso8601) < (now - 259200))] | length')
  [ "$count" = "0" ]
max_iterations: 50
cost_budget: 5.00
isolation: worktree
```

### 11.2 Goal-based refactor loop (Codex `/goal`)

```yaml
goal: "All functions in src/legacy/*.py have type hints and pass mypy --strict"
verification: mypy src/legacy --strict
maker_self_check: pytest tests/legacy
max_attempts: 5
escalation: "open issue with full diff if max_attempts hit"
```

### 11.3 Hook loop — auto-triage on PR

```yaml
trigger: pull_request.opened
loop_type: hook
actions:
  - run: pr-classifier sub-agent (flake / bug / env / dep)
  - on bug: spawn implementer in worktree, run tests, comment draft fix
  - on env: post checklist, label needs-env
  - on dep: open rollback PR if last release changed deps
stop: pr labeled "needs-human"
```

### 11.4 Heartbeat loop — service drift detector

```yaml
schedule: every 5 minutes
loop_type: heartbeat
check: |
  if [ "$(curl -sS http://service/health | jq -r .status)" != "ok" ]; then
    spawn debugger-subagent
    create incident
  fi
cost_budget: 2.00/day
```

---

## 12. Adoption Checklist (for Master Yang)

If you want to operationalise loop engineering in your stack, here's a concrete first-90-days path:

### Phase 1 — Pick one loop-shaped job
- [ ] Identify one task you do manually ≥ 3× per week
- [ ] Verify it passes the 4-condition suitability test (repetitive, verifiable success, reversible, bounded cost)
- [ ] Examples for your stack: Molt board archival, Streamlit health check, flight price monitor, daily LinkedIn AI jobs scan, dependency update PRs

### Phase 2 — Build the loop in your existing tool
- [ ] Claude Code: write a `~/.claude/commands/<name>.md` with schedule + verification + max_iterations
- [ ] Codex: create an Automation in the Automations tab
- [ ] Start with `max_iterations: 50` and a tight `cost_budget`

### Phase 3 — Add the safety rails
- [ ] **Two gates:** `verification_command` (maker) + `goal_check_command` (independent checker)
- [ ] **Stop rules:** `max_attempts: 3`, repeated-failure detection
- [ ] **Budget cap:** daily dollar limit, alert on 80%
- [ ] **Worktree isolation:** every run gets its own checkout
- [ ] **No auto-merge:** humans always review the PR

### Phase 4 — Observe and tune
- [ ] Track: acceptance rate (PRs merged / PRs opened), cost per run, escalation rate
- [ ] Add lessons learned to state file after each run
- [ ] Promote the skill (`SKILL.md`) once it's stable

### Phase 5 — Compose
- [ ] Combine loops: cron loop opens a goal loop on finding, goal loop spawns a sub-agent, sub-agent fires a hook on verification failure
- [ ] Share plugins across repos
- [ ] Apply the **"stay the engineer"** discipline: read the diffs the loop ships, don't just merge them

---

## 13. Critical Reading & Scepticism

Things to push back on when you hear loop engineering evangelised:

1. **"It's just a cron job."** Sort of, but the value is in the *verify-decide-iterate* control flow, not the trigger. A cron job that runs `pytest` once is not a loop. A cron job that reads pytest output, decides whether to fix or escalate, and only stops when the suite is green — that is.

2. **"Loops replace engineers."** No. The framework is explicit: the human is still the ceiling on review bandwidth. Loops amplify engineers, they don't substitute for engineering judgement.

3. **"Frontier models make this cheap."** No. A goal loop with no budget cap and no per-step model routing is a credit card with a heartbeat. Routing + caching is what makes it economical.

4. **"Works for any task."** No. The suitability test exists. Architecture decisions, auth/payment code, and unclear-spec work are explicitly out of scope.

5. **"Just install loop-mcp and you're done."** No. The package is a *reference implementation* of the framework, not the framework itself. The value is in your skill files, your goal definitions, your stop conditions, and your review discipline. The package gives you the wiring.

6. **"It's a totally new idea."** Half-true. The pattern is as old as control theory (sense → decide → act). What's new is that the actor is an LLM and the language of the goal is natural. The novelty is in the *blend*, not the *parts*.

---

## 14. Verdict

Loop engineering is a coherent and useful framework, not just a marketing label. The five primitives + memory pattern is concrete, the reference implementation (`loop-mcp`) is small and inspectable, and the failure modes are well-documented. The most valuable contribution is not the parts but the **discipline**: maker/checker separation, no-progress detection, budget caps, worktree isolation, and the explicit "stay the engineer" reminder.

For Master Yang, the practical implication is: **the next level of leverage is to take tasks you currently prompt me to do (flight monitoring, daily LinkedIn scan, kanban archival, daily progress digest) and design them as loops with explicit verify-decide-iterate cycles, worktree isolation, and budget caps** — rather than relying on me to be prompted each time. I already have most of the pieces (MCP, scheduled tasks, sub-agents via `sessions_spawn`); the missing piece is formalising the control loop with two gates, stop rules, and on-disk state.

**Recommended first loop to build:** the daily LinkedIn AI jobs scan, refactored from a single cron into a loop with:
- **Goal check:** "all 23 known jobs still exist + any new job is appended with a Link"
- **Maker:** the scan sub-agent
- **Checker:** an independent verifier that confirms the file is valid Markdown and the summary tables are consistent
- **Stop rules:** escalate if the same scan error repeats twice, daily cost cap
- **State:** `C:\code\interview-prep\notes\YL-notes\online-resources\AI-jobs.md` (already the canonical file) becomes the durable state

That's a one-week project that would close the loop on a job you already have a cron for. After that, the pattern generalises.

---

*Report compiled 2026-07-23. Sources current as of compile date; loop engineering is a fast-moving space (Osmani post: Jun 7, 2026; `loop-mcp` v0.4.0: current; Requesty analysis: Jun 17, 2026). Re-check primary sources before treating any of this as definitive.*
