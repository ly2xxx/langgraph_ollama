# Patch Engineer (`patch_engineer`) Specification

## 1. Overview & Vision

**Patch Engineer** is an autonomous DevSecOps and Dependency Migration agent built on [LangGraph](https://github.com/langchain-ai/langgraph). It automates complex dependency upgrades, CVE remediation, and breaking API migrations across software repositories with zero human intervention and mathematical safety guarantees.

Unlike simple automated PR bots (e.g., Dependabot, Renovate) that only bump version numbers and leave failing builds for developers, **Patch Engineer**:
1. Isolates the target repository in a sandboxed Git worktree.
2. Audits baseline CVE vulnerabilities and security findings (Trivy, Pip-Audit, Semgrep, Bandit).
3. Authors behavioral specifications and BDD acceptance criteria to preserve existing application semantics.
4. Uses Tree-of-Thought (ToT) planning to select optimal migration strategies (AST codemods vs. surgical refactoring vs. compatibility shims).
5. Executes sandboxed patching tools (`uv`, `ast-grep`, `ruff`, AST transformers).
6. Enforces multi-layered quality gates: **Differential Security/SAST Gate** $\rightarrow$ **BDD Regression Test Gate** $\rightarrow$ **Adversarial Security Auditor** (detecting `# nosec` hacks or dependency wildcards).
7. Uses SHA-1 failure signature hashing to detect no-progress loops and pivot plans dynamically.

---

## 2. Architecture & State Graph

```
                        ┌────────────────────────┐
                        │      intake_node       │
                        └───────────┬────────────┘
                                    │
                        ┌───────────▼────────────┐
                        │    author_spec_node    │
                        └───────────┬────────────┘
                                    │
                        ┌───────────▼────────────┐
                        │     plan_tot_node      │◄────────────────┐
                        └───────────┬────────────┘                 │
                                    │                              │
                        ┌───────────▼────────────┐                 │
                        │       patch_node       │                 │ (New Strategy)
                        └───────────┬────────────┘                 │
                                    │                              │
                        ┌───────────▼────────────┐                 │
                        │   security_gate_node   │                 │
                        └───────────┬────────────┘                 │
                              Passed│ Failed                       │
                        ┌───────────▼────────────┐                 │
                        │     test_gate_node     │                 │
                        └───────────┬────────────┘                 │
                              Passed│ Failed                       │
                        ┌───────────▼────────────┐                 │
                        │  security_review_node  │                 │
                        └───────────┬────────────┘                 │
                        Approved    │ Rejected                     │
             ┌──────────────────────┴────────────┐       ┌─────────┴──────────┐
             │                                   ├──────►│   diagnose_node    │
             ▼                                   │       └─────────┬──────────┘
 ┌───────────────────────┐                       │                 │ (Retry / Escalate)
 │     finalize_node     │                       │                 ▼
 └───────────────────────┘                       │       ┌────────────────────┐
                                                 └──────►│   escalate_node    │
                                                         └────────────────────┘
```

---

## 3. Core Component Specifications

### 3.1 State Schema (`CodingLoopState` extension for Security)
Defined in `patch_engineer/state.py`:
- `cve_targets`: List of target CVE IDs or dependency upgrade targets (e.g. `["CVE-2024-23334", "pydantic>=2.0"]`).
- `baseline_vulnerabilities`: Initial Trivy / Pip-Audit finding dicts.
- `security_findings`: Current security scanning results.
- `sast_findings`: Semgrep / Bandit findings.
- `ast_diff_summary`: AST changes summary.
- `adversarial_review_verdict`: Approval status from secondary Security Auditor.

### 3.2 Key Nodes

| Node Name | Input State | Output State | Purpose |
| :--- | :--- | :--- | :--- |
| `intake_node` | Goal, target_dir | Worktree, baseline_vulnerabilities | Creates Git worktree; runs baseline vulnerability scan & lockfile analysis. |
| `author_spec_node` | Goal, spec | BDD feature files, test_baseline | Authors BDD acceptance scenarios for the dependency migration target. |
| `plan_tot_node` | spec, lessons | candidate_plans, active_plan | Proposes $k$ migration strategies (Codemod vs Shim vs Refactor); scores via Security Judge. |
| `patch_node` | active_plan, worktree | git diff, changes | Applies automated codemods (`ast-grep`, `ruff`) and manual LLM surgical edits. |
| `security_gate_node` | worktree | security_findings, sast_findings | Runs `pip-audit`/`trivy` and `semgrep`/`bandit`. Fails if CVE persists or new SAST bugs introduced. |
| `test_gate_node` | worktree | test_report, bdd_report | Runs unit and BDD tests against worktree. |
| `security_review_node`| git diff, findings | review_result (Approved/Rejected) | Secondary LLM audits diff against security bypass hacks (`# nosec`, wildcards, suppressed tests). |
| `diagnose_node` | test_report, findings | signature, lesson, action | Computes normalized SHA-1 failure signature; detects no-progress loops; switches plans. |

---

## 4. Quality & Security Gates

1. **Vulnerability Resolution Gate**:
   - `pip-audit --format=json` / `trivy fs --format json .`
   - Zero target CVEs remaining; zero newly added CVEs.
2. **SAST Baseline Gate**:
   - `semgrep --config p/security-audit` / `bandit -r .`
   - Ensures no high/medium security vulnerabilities introduced during migration.
3. **Behavioral Acceptance Gate**:
   - `pytest` suite + pytest-bdd scenarios pass 100%.
4. **Adversarial Audit Gate**:
   - Secondary Security Judge rejects any diff containing:
     - `# nosec` or `# type: ignore` suppressing security alerts.
     - Commenting out or modifying test assertions without explicit specification.
     - Insecure dependency version pins (e.g. `*`, `>=0.0.0`).

---

## 5. Failure Signature Schema

$$
\text{Signature} = \text{SHA1}(\text{Phase} \mid \text{Normalized Error Class} \mid \text{Dependency Package} \mid \text{Top Frame Function})
$$

If `signature == prev_signature` across consecutive attempts:
1. Current migration plan is retired.
2. Lessons learned are recorded.
3. ToT Planner re-scores surviving plans or generates alternative codemod strategies.
4. Escalates to human after 2 plans exhausted.
