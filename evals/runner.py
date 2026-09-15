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
    "max_plans": 2,
    "max_total_attempts": 5,
    "cmd_timeout_s": 120,
    "wall_clock_s": 900,
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


def materialise(task: dict, root: Path) -> None:
    """Seed repo + git init. The agent needs a real git repo to branch a worktree from."""
    _write_files(root, task["seed"])
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=eval@local", "-c", "user.name=eval",
         "commit", "-q", "-m", "seed"],
        cwd=root, check=True,
    )


def run_agent(task: dict, target: Path) -> tuple[int, bool, str | None]:
    """Drive the real agent. Returns (total_attempts, escalated, harness_error)."""
    from coding_agent.engine import stream_run, new_run_id

    run_id = new_run_id()
    final: dict = {}
    try:
        for update in stream_run(run_id, str(target), task["goal"], hitl=False,
                                 budgets=dict(DEFAULT_BUDGETS)):
            for node_name, node_update in update.items():
                if node_name == "__interrupt__" or not isinstance(node_update, dict):
                    continue
                final.update(node_update)
    except Exception as exc:  # harness/infra failure, not an agent failure
        return 0, False, f"{type(exc).__name__}: {exc}"

    attempts = int(final.get("total_attempts") or final.get("attempt") or 1)
    status = str(final.get("status") or "")
    escalated = "escalat" in status.lower() or "budget" in status.lower()
    return attempts, escalated, None


def verify(task: dict, target: Path) -> tuple[bool, str]:
    """Write the hidden tests and run them against whatever the agent left behind."""
    _write_files(target, task["verify"]["files"])
    proc = subprocess.run(
        task["verify"]["cmd"], cwd=target, capture_output=True, text=True,
        timeout=300, env={**os.environ, "PYTHONPATH": str(target)},
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-12:]
    return proc.returncode == 0, "\n".join(tail)


def score_one(task: dict, keep: bool = False) -> TaskResult:
    started = time.time()
    tmp = Path(tempfile.mkdtemp(prefix=f"eval-{task['id']}-"))
    target = tmp / "repo"
    target.mkdir()
    try:
        materialise(task, target)
        attempts, escalated, err = run_agent(task, target)
        if err:
            return TaskResult(task["id"], task["category"], task["difficulty"],
                              False, attempts, escalated, time.time() - started, error=err)
        solved, tail = verify(task, target)
        return TaskResult(task["id"], task["category"], task["difficulty"],
                          solved, attempts, escalated, time.time() - started,
                          test_output_tail=tail)
    finally:
        if keep:
            print(f"    workspace kept: {target}")
        else:
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
              + (f" ERROR {res.error}" if res.error else ""))

    print(report.render())
    if args.out:
        args.out.write_text(json.dumps(report.to_dict(), indent=2))
        print(f"\nJSON report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
