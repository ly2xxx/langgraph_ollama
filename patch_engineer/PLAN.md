# Patch Engineer (`patch_engineer`) Implementation Plan

> **For Autonomous Coding Agent Execution**  
> This implementation plan outlines the step-by-step development of **Patch Engineer**—an autonomous DevSecOps and dependency migration agent based on LangGraph.  
> Follow the tasks sequentially, running test commands after completing each subtask.

---

## Task Checklist & Execution Progress

- [ ] `[Phase 1]` **Module Structure & Core State Schema**
  - [ ] `[Task 1.1]` Create `patch_engineer/` directory layout (`__init__.py`, `state.py`, `schemas.py`).
  - [ ] `[Task 1.2]` Implement `SecurityBudgets` and `PatchEngineerState` in `patch_engineer/state.py`.
  - [ ] `[Task 1.3]` Implement Pydantic output schemas in `patch_engineer/schemas.py` (`TargetSecuritySpec`, `MigrationPlanProposal`, `SecurityReviewVerdict`).
- [ ] `[Phase 2]` **Security Tools & Worktree Sandboxing**
  - [ ] `[Task 2.1]` Implement Git worktree isolation in `patch_engineer/tools/worktree.py`.
  - [ ] `[Task 2.2]` Implement security scanner runners in `patch_engineer/tools/security_exec.py` (`run_pip_audit`, `run_trivy`, `run_semgrep`, `run_bandit`).
  - [ ] `[Task 2.3]` Build `SecurityJail` sandbox wrapping filesystem modifications and dependency installer commands (`uv pip`, `ast-grep`, `ruff`).
- [ ] `[Phase 3]` **Intake & Behavioral Spec Nodes**
  - [ ] `[Task 3.1]` Implement `intake_node` in `patch_engineer/nodes.py` (clones worktree, runs baseline scanner, analyzes lockfiles).
  - [ ] `[Task 3.2]` Implement `author_spec_node` (authors BDD acceptance tests for migration targets).
- [ ] `[Phase 4]` **ToT Migration Strategy Planner**
  - [ ] `[Task 4.1]` Implement dual-model resolver in `patch_engineer/models.py` (`primary` for propose/patch, `secondary` for security judge/review).
  - [ ] `[Task 4.2]` Implement `plan_tot_node` with dynamic lesson re-scoring (proposes $k$ migration strategies: Codemod vs Refactor vs Compatibility Shim).
- [ ] `[Phase 5]` **Patch Execution (Maker) Node**
  - [ ] `[Task 5.1]` Build Maker tool definitions in `patch_engineer/maker_tools.py` (`read_file`, `write_file`, `ast_grep_replace`, `uv_pip_install`, `run_pytest`).
  - [ ] `[Task 5.2]` Implement `patch_node` in `patch_engineer/nodes.py` executing the sandbox Maker agent loop.
- [ ] `[Phase 6]` **Multi-Layer Quality & Security Gates**
  - [ ] `[Task 6.1]` Implement security gate checks in `patch_engineer/gates.py` (`audit_cve_resolution()`, `audit_sast_regressions()`).
  - [ ] `[Task 6.2]` Implement `security_gate_node` and `test_gate_node` in `patch_engineer/nodes.py`.
- [ ] `[Phase 7]` **Adversarial Security Auditor & Circuit Breaker**
  - [ ] `[Task 7.1]` Implement `security_review_node` auditing `git diff` against security bypass tricks (`# nosec`, `# type: ignore`, wildcard pins).
  - [ ] `[Task 7.2]` Implement failure signature SHA-1 hashing in `patch_engineer/signatures.py` (`compute_patch_failure_signature()`).
  - [ ] `[Task 7.3]` Implement `diagnose_node` for no-progress signature detection and automatic strategy switching.
- [ ] `[Phase 8]` **Engine Graph Assembly & CLI**
  - [ ] `[Task 8.1]` Build LangGraph state machine in `patch_engineer/engine.py` with `SqliteSaver` checkpointing.
  - [ ] `[Task 8.2]` Build report generator in `patch_engineer/report.py` (`PATCH_REPORT.md`).
  - [ ] `[Task 8.3]` Add CLI entry point supporting `--target`, `--cve`, `--goal`, and `--run-id` resume flags.
- [ ] `[Phase 9]` **End-to-End Verification**
  - [ ] `[Task 9.1]` Create sample vulnerable repository target in `patch_engineer/sample_target/` with known vulnerable dependencies (`requests<2.31.0` or `pydantic<2.0`).
  - [ ] `[Task 9.2]` Execute full end-to-end patch run and verify clean resolution.

---

## Detailed Implementation Guidance

### Phase 1: Module Structure & Core State Schema

#### Files to Create:
- `patch_engineer/__init__.py`
- `patch_engineer/state.py`
- `patch_engineer/schemas.py`

#### `patch_engineer/state.py` Requirements:
```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class SecurityBudgets(TypedDict):
    max_attempts_per_plan: int
    max_plans: int
    max_total_attempts: int
    cmd_timeout_s: int
    wall_clock_s: int

class PatchEngineerState(TypedDict, total=False):
    run_id: str
    target_dir: str
    worktree_dir: str
    branch: str
    goal: str
    cve_targets: list[str]
    budgets: SecurityBudgets
    model_info: dict

    # Intake & Spec
    spec: dict
    feature_paths: list[str]
    baseline_vulnerabilities: list[dict]

    # ToT Planning
    candidate_plans: list[dict]
    active_plan_id: str
    lessons: list[dict]

    # Execution & Auditing
    attempt: int
    total_attempts: int
    last_diff: str
    security_report: dict
    sast_report: dict
    test_report: dict
    review_result: dict | None
    escalation_reason: str | None

    # Circuit breaking
    failure_signature: str | None
    prev_failure_signature: str | None
    exhausted_plan_ids: list[str]

    # Outcome
    status: str
    messages: Annotated[list, add_messages]
```

---

### Phase 2: Security Tools & Worktree Sandboxing

#### Files to Create:
- `patch_engineer/tools/__init__.py`
- `patch_engineer/tools/worktree.py`
- `patch_engineer/tools/security_exec.py`

#### Key Capabilities in `security_exec.py`:
1. `run_pip_audit(worktree_dir: str) -> dict`: Parses `pip-audit --format=json`.
2. `run_trivy(worktree_dir: str) -> dict`: Parses `trivy fs --format json`.
3. `run_semgrep(worktree_dir: str) -> dict`: Runs `semgrep --config p/security-audit --json`.
4. `run_bandit(worktree_dir: str) -> dict`: Runs `bandit -r . -f json`.

---

### Phase 3: Intake & Behavioral Spec Nodes

#### Intake Logic (`nodes/intake.py`):
1. Creates isolated Git branch `patch-engineer/<run_id>` in `.loop/worktrees/`.
2. Executes baseline scanner (`pip-audit` / `trivy`).
3. Extracts lockfile dependencies (`requirements.txt`, `pyproject.toml`).
4. Constructs `TargetSecuritySpec` using primary LLM.

---

### Phase 4: Tree-of-Thought (ToT) Security Planner

#### Planner Strategies to Propose:
1. **Strategy A (Automated AST Codemod)**: Uses `ast-grep` or `ruff --fix` for deterministic API replacement.
2. **Strategy B (Surgical Refactoring)**: In-place manual refactoring of deprecated imports and method calls.
3. **Strategy C (Compatibility Shim)**: Introduces a lightweight adapter module to preserve existing call signatures while using the updated underlying library.

---

### Phase 5: Patch Execution (Maker) Node

#### Maker Tools (`maker_tools.py`):
- `read_file(path)`
- `write_file(path, content)`
- `ast_grep_replace(pattern, rewrite)`
- `run_pytest(subpath)`
- `run_security_check()`

#### Security Jail:
Wrap all file writing tools to prevent modifying:
- `.feature` BDD spec files.
- Files outside the target `worktree_dir`.

---

### Phase 6: Security & SAST Gates

#### Differential Security Logic:
- `audit_cve_resolution()`: Confirms all specified `cve_targets` are absent from `pip-audit` / `trivy` output.
- `audit_sast_regressions()`: Compares `semgrep` findings against initial baseline. Fails if NEW high/medium SAST issues exist.

---

### Phase 7: Adversarial Security Auditor & Circuit Breaker

#### System Prompt for `security_review_node`:
```
You are an adversarial DevSecOps Security Auditor.
Your job is to inspect the git diff of a dependency patch and REJECT it if the agent attempted any of the following bypass tricks:
1. Added '# nosec', '# type: ignore', or suppressed linter/security warnings.
2. Modified test assertions to trivially pass (e.g. replacing 'assert x == 200' with 'assert True').
3. Pinned dependencies to wildcard '*' or unvetted external repositories.
4. Left hardcoded secrets, tokens, or debugging backdoors.
```

#### Failure Signature Calculation (`signatures.py`):
```python
import hashlib, re

def compute_patch_failure_signature(phase: str, error_msg: str, top_frame: str) -> str:
    cleaned = re.sub(r'0x[0-9a-fA-F]+', '<HEX>', error_msg)
    cleaned = re.sub(r'\d+', '<NUM>', cleaned)
    raw = f"{phase}|{cleaned[:100]}|{top_frame}"
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]
```

---

### Phase 8: Engine Graph Assembly & CLI

#### Graph Nodes & Routing:
- `intake` $\rightarrow$ `author_spec` $\rightarrow$ `plan_tot` $\rightarrow$ `patch` $\rightarrow$ `security_gate`
- `security_gate`:
  - `Passed` $\rightarrow$ `test_gate`
  - `Failed` $\rightarrow$ `diagnose`
- `test_gate`:
  - `Passed` $\rightarrow$ `security_review`
  - `Failed` $\rightarrow$ `diagnose`
- `security_review`:
  - `Approved` $\rightarrow$ `finalize`
  - `Rejected` $\rightarrow$ `diagnose`
- `diagnose`:
  - `Retry` $\rightarrow$ `patch`
  - `Switch Plan` $\rightarrow$ `plan_tot`
  - `Escalate` $\rightarrow$ `escalate`

---

## Verification Plan

### Automated Tests
Run pytest over the `patch_engineer` codebase:
```bash
pytest patch_engineer/tests/ -v
```

### End-to-End Test Run
Execute Patch Engineer against sample target:
```bash
python -m patch_engineer.engine --target patch_engineer/sample_target --cve "CVE-2023-32681" --goal "Upgrade requests to >=2.31.0 and fix security vulnerabilities"
```

Verify `PATCH_REPORT.md` is generated and status is `completed`.
