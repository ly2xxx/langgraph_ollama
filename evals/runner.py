"""Run the Coding Engineer agent against the eval dataset and score it by execution.

Flow per task:
  1. materialise the seed repo into a fresh temp dir and `git init` it
     (the agent works in a git worktree off the target dir)
  2. run the agent to completion via coding_agent.engine.stream_run, capturing
     the final state (total_attempts, status)
  3. ONLY THEN write the hidden verification tests into the worktree and run
     pytest against the code the agent produced
  4. record solved / attempts / escalated

Step 3 is the design point: the agent never sees the tests it is scored on, so
the score cannot be gamed by writing assertions that match the implementation.

Usage:
    python -m evals.runner                    # full run
    python -m evals.runner --tasks bug-001 feat-002
    python -m evals.runner --validate         # no LLM: check the dataset is sane
    python -m evals.runner --out results.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.metrics import EvalReport, TaskResult  # noqa: E402

DATASET = Path(__file__).parent / "dataset.json"
DEFAULT_BUDGETS = {
    "max_attempts_per_plan": 3,
    # max_plans is the tree-of-thoughts candidate count (nodes.py `k`), NOT a
    # replan budget. 2 narrowed the search below the code's own default of 3.
    "max_plans": 3,
    "max_total_attempts": 5,
    "cmd_timeout_s": 120,
    "wall_clock_s": 2400,
    "token_budget": 200_000,
}


def load_tasks(only: list[str] | None = None) -> list[dict]:
    data = json.loads(DATASET.read_text())
    tasks = data["tasks"]
    if only:
        wanted = set(only)
        tasks = [t for t in tasks if t["id"] in wanted]
        missing = wanted - {t["id"] for t in tasks}
        if missing:
            raise SystemExit(f"unknown task id(s): {', '.join(sorted(missing))}")
    return tasks


def _write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def materialise(task: dict, root: Path) -> str:
    """Seed repo + git init. The agent needs a real git repo to branch a worktree from."""
    _write_files(root, task["seed"])
    # Seed a visible smoke test. Without it `tests/` does not exist, so the agent's
    # self_check gate collects zero tests and reports passed=true while src/ is
    # still a stub -- the agent is told it is done and spends its whole budget on
    # the only gate that does fail, its own BDD harness. The hidden acceptance
    # tests stay hidden; this only asserts the required symbol exists.
    _write_files(root, task.get("smoke", {}))
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=eval@local", "-c", "user.name=eval",
         "commit", "-q", "-m", "seed"],
        cwd=root, check=True,
    )
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                         capture_output=True, text=True, check=True)
    return sha.stdout.strip()


def run_agent(task: dict, target: Path) -> tuple[int, bool, str, Path | None, str | None]:
    """Drive the real agent. Returns (total_attempts, escalated, worktree_dir, harness_error).

    The agent does NOT write into `target`. coding_agent.tools.worktree.create_worktree
    puts every run in <loop_state_dir>/worktrees/<run_id> on branch
    coding-engineer/<run_id>, and that branch is never merged back. So we capture
    `worktree_dir` off the intake node's state update and verify THERE -- verifying
    `target` would score the pristine seed, which fails by construction.
    """
    from coding_agent.engine import stream_run, new_run_id

    run_id = new_run_id()
    final: dict = {}
    # Mirror run_cli's per-node trace. Without it this harness is a black box and
    # a failure is indistinguishable from a hang -- which cost a day of guessing
    # at behaviour the agent was reporting all along.
    print(f"    run_id={run_id}")
    try:
        for update in stream_run(run_id, str(target), task["goal"], hitl=False,
                                 budgets=dict(DEFAULT_BUDGETS)):
            for node_name, node_update in update.items():
                if node_name == "__interrupt__":
                    print(f"    [INTERRUPTED] {node_update}")
                    continue
                if not isinstance(node_update, dict):
                    continue
                st = node_update.get("status")
                print(f"    [{node_name}]" + (f" status={st}" if st else ""), flush=True)
                final.update(node_update)
    except Exception as exc:  # harness/infra failure, not an agent failure
        return 0, False, str(final.get("escalation_reason") or ""), _worktree_of(final), f"{type(exc).__name__}: {exc}"

    attempts = int(final.get("total_attempts") or final.get("attempt") or 1)
    status = str(final.get("status") or "")
    escalated = "escalat" in status.lower() or "budget" in status.lower()
    # The loop records WHY it gave up -- "unsuitable goal", "no_plans_left",
    # "intake structured-output failure: ...". Three of the six escalation paths
    # have nothing to do with coding ability, so a bare escalated=True flag
    # cannot distinguish a weak model from a loop that never reached the code.
    reason = str(final.get("escalation_reason") or "")
    print(f"    report: {report_path_for(run_id)}")
    wt = _worktree_of(final)
    if wt is None:
        return attempts, escalated, reason, None, "agent produced no worktree_dir (intake failed?)"
    return attempts, escalated, reason, wt, None


def report_path_for(run_id: str) -> Path:
    """Same location run_cli prints. The loop writes a report on BOTH outcomes --
    done and escalated -- so there is always one to read after a failed task."""
    from coding_agent.nodes import _loop_state_dir
    return _loop_state_dir() / "state" / "coding-engineer" / run_id / "run-report.md"


def _worktree_of(state: dict) -> Path | None:
    wt = state.get("worktree_dir")
    if not wt:
        return None
    p = Path(wt)
    return p if p.exists() else None


def cleanup_worktree(target: Path, worktree: Path | None) -> None:
    """Remove the run's worktree. It lives OUTSIDE the temp dir, so rmtree of the
    workspace does not reclaim it -- and create_worktree() raises WorktreeError if
    the directory already exists, so leftovers break later runs.
    """
    if worktree is None or not worktree.exists():
        return
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree)],
                   cwd=target, capture_output=True, text=True)
    if worktree.exists():           # fallback-copy path: not a real worktree
        shutil.rmtree(worktree, ignore_errors=True)


def agent_changed_files(worktree: Path | None, seed_sha: str) -> list[str]:
    """Files the agent touched, diffed against the exact seed commit.

    Computed BEFORE the hidden tests are written, so it reflects the agent's work
    only. Diffing the working tree against `seed_sha` catches both committed and
    uncommitted changes in one shot -- `HEAD~1..HEAD` does not, because the
    worktree branches off a single-commit history and that range lists the seed's
    own files as though the agent had written them.

    An empty list on a FAIL means the agent never produced a change: a completely
    different problem from producing a wrong one.
    """
    if worktree is None or not seed_sha:
        return []
    proc = subprocess.run(["git", "diff", "--name-only", seed_sha],
                          cwd=worktree, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return sorted(f for f in proc.stdout.split()
                  if f and "__pycache__" not in f and not f.endswith(".pyc"))


def verify(task: dict, target: Path) -> tuple[bool, str]:
    """Write the hidden tests and run them against whatever the agent left behind.

    `target` is the agent's WORKTREE, not the seed dir -- see run_agent().
    A hang or crash here is scored as a failed task, never allowed to abort the
    whole run: one pathological task must not cost the other seven.
    """
    _write_files(target, task["verify"]["files"])
    # Run the SAME interpreter this harness is running under. A bare "python"
    # resolves through PATH, which on Windows under uv picked the uv-managed
    # CPython rather than the project venv -- so pytest was not importable and
    # every task scored FAIL with "No module named pytest", whatever the agent did.
    cmd = list(task["verify"]["cmd"])
    if cmd and cmd[0] in ("python", "python3", "py"):
        cmd[0] = sys.executable
    try:
        proc = subprocess.run(
            cmd, cwd=target, capture_output=True, text=True,
            timeout=300, env={**os.environ, "PYTHONPATH": str(target)},
        )
    except subprocess.TimeoutExpired:
        return False, "verification timed out after 300s"
    except OSError as exc:
        return False, f"could not run verification ({cmd[0]}): {exc}"
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-12:]
    return proc.returncode == 0, "\n".join(tail)


def score_one(task: dict, keep: bool = False) -> TaskResult:
    started = time.time()
    worktree: Path | None = None
    tmp = Path(tempfile.mkdtemp(prefix=f"eval-{task['id']}-"))
    target = tmp / "repo"
    target.mkdir()
    try:
        seed_sha = materialise(task, target)
        attempts, escalated, reason, worktree, err = run_agent(task, target)
        if err:
            return TaskResult(task["id"], task["category"], task["difficulty"],
                              False, attempts, escalated, time.time() - started,
                              error=err, escalation_reason=reason)
        # Verify in the worktree -- that is where the agent's code actually is.
        changed = agent_changed_files(worktree, seed_sha)
        solved, tail = verify(task, worktree)
        return TaskResult(task["id"], task["category"], task["difficulty"],
                          solved, attempts, escalated, time.time() - started,
                          test_output_tail=tail, changed_files=changed,
                          escalation_reason=reason)
    finally:
        if keep:
            print(f"    workspace kept: {target}")
            if worktree:
                print(f"    worktree kept:  {worktree}")
        else:
            cleanup_worktree(target, worktree)
            shutil.rmtree(tmp, ignore_errors=True)


def selftest_only(tasks: list[dict]) -> int:
    """No LLM required: apply each task's reference solution and prove the hidden
    tests PASS. A task whose tests fail here is unsolvable and would depress the
    agent's score for reasons that have nothing to do with the agent."""
    bad = 0
    for t in tasks:
        tmp = Path(tempfile.mkdtemp(prefix=f"self-{t['id']}-"))
        target = tmp / "repo"
        target.mkdir()
        try:
            _write_files(target, t["seed"])
            _write_files(target, t["reference"])
            solved, tail = verify(t, target)
            if solved:
                print(f"  [ok  ] {t['id']}: reference solution passes")
            else:
                print(f"  [BAD ] {t['id']}: reference solution FAILS -- task unsolvable")
                print("         " + tail.replace("\n", "\n         "))
                bad += 1
        except Exception as exc:
            print(f"  [ERR ] {t['id']}: {type(exc).__name__}: {exc}")
            bad += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(tasks) - bad}/{len(tasks)} tasks solvable")
    return 1 if bad else 0


def validate_only(tasks: list[dict]) -> int:
    """No LLM required: prove each task's seed FAILS and a reference fix would be
    detectable -- i.e. the hidden tests actually discriminate."""
    bad = 0
    for t in tasks:
        tmp = Path(tempfile.mkdtemp(prefix=f"val-{t['id']}-"))
        target = tmp / "repo"
        target.mkdir()
        try:
            _write_files(target, t["seed"])
            solved, tail = verify(t, target)
            if solved:
                print(f"  [BAD ] {t['id']}: hidden tests PASS on the unfixed seed "
                      f"-- task is a no-op, fix the seed")
                bad += 1
            else:
                print(f"  [ok  ] {t['id']}: seed fails as expected ({t['difficulty']})")
        except Exception as exc:
            print(f"  [ERR ] {t['id']}: {type(exc).__name__}: {exc}")
            bad += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(tasks) - bad}/{len(tasks)} tasks valid")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", nargs="*", help="task ids to run (default: all)")
    ap.add_argument("--validate", action="store_true",
                    help="check the dataset discriminates, without running the agent")
    ap.add_argument("--selftest", action="store_true",
                    help="check each task is solvable via its reference solution")
    ap.add_argument("--out", type=Path, help="write the full JSON report here")
    ap.add_argument("--keep", action="store_true", help="keep temp workspaces for inspection")
    args = ap.parse_args()

    tasks = load_tasks(args.tasks)

    if args.selftest:
        print(f"self-testing {len(tasks)} task(s) -- reference solutions must PASS\n")
        return selftest_only(tasks)

    if args.validate:
        print(f"validating {len(tasks)} task(s) -- hidden tests must FAIL on the seed\n")
        return validate_only(tasks)

    report = EvalReport()
    for i, t in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {t['id']} ({t['difficulty']}) ...", flush=True)
        res = score_one(t, keep=args.keep)
        report.results.append(res)
        print(f"    -> {'PASS' if res.solved else 'FAIL'} "
              f"attempts={res.attempts} {res.wall_clock_s:.1f}s"
              + (" ESCALATED" if res.escalated else "")
              + (f"\n       escalation_reason: {res.escalation_reason}"
                 if res.escalation_reason else "")
              + (f" ERROR {res.error}" if res.error else ""))
        if not res.solved and res.test_output_tail:
            # The single most useful line in a failed run: an ImportError here
            # means the harness could not reach the agent's code, an assertion
            # failure means the agent's code was simply wrong. Very different bugs.
            print("    --- verification output ---")
            for line in res.test_output_tail.splitlines():
                print(f"    | {line}")
        if not res.solved and res.changed_files:
            print(f"    --- agent changed {len(res.changed_files)} file(s): "
                  f"{', '.join(res.changed_files[:8])}")

    print(report.render())
    if args.out:
        args.out.write_text(json.dumps(report.to_dict(), indent=2))
        print(f"\nJSON report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
