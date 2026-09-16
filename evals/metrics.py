"""Execution-based metrics for the Coding Engineer agent.

Every metric here is derived from *running hidden tests against the code the
agent actually produced* -- never from an LLM judging its own output. That is
the whole point: the numbers are reproducible and the agent cannot game them,
because the verification tests are written into the worktree only after the
agent has finished and committed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from statistics import mean


@dataclass
class TaskResult:
    task_id: str
    category: str
    difficulty: str
    solved: bool                 # hidden tests passed at the end of the run
    attempts: int                # total_attempts the agent burned
    escalated: bool              # agent gave up / hit budget
    wall_clock_s: float
    error: str | None = None     # harness-level failure, not an agent failure
    test_output_tail: str = ""
    changed_files: list[str] = field(default_factory=list)
    escalation_reason: str = ""   # why the loop gave up, straight from state

    @property
    def valid(self) -> bool:
        """Harness errors are excluded from rates rather than counted as agent failures."""
        return self.error is None


@dataclass
class EvalReport:
    results: list[TaskResult] = field(default_factory=list)

    @property
    def scored(self) -> list[TaskResult]:
        return [r for r in self.results if r.valid]

    def _rate(self, num: int) -> float:
        n = len(self.scored)
        return round(num / n, 4) if n else 0.0

    @property
    def pass_at_1(self) -> float:
        """Solved on the agent's first attempt, with no self-correction loop."""
        return self._rate(sum(1 for r in self.scored if r.solved and r.attempts <= 1))

    @property
    def solve_rate(self) -> float:
        """Solved at any point within budget (Pass@k)."""
        return self._rate(sum(1 for r in self.scored if r.solved))

    @property
    def recovery_rate(self) -> float:
        """Of the tasks that failed on attempt 1, the share the loop went on to solve.

        This is the metric that actually measures the agent harness rather than the
        underlying model -- it isolates the value added by conditional routing and
        the failure-signature feedback in state.
        """
        recoverable = [r for r in self.scored if r.attempts > 1]
        if not recoverable:
            return 0.0
        return round(sum(1 for r in recoverable if r.solved) / len(recoverable), 4)

    @property
    def escalation_rate(self) -> float:
        return self._rate(sum(1 for r in self.scored if r.escalated))

    @property
    def mean_attempts_to_solve(self) -> float:
        solved = [r.attempts for r in self.scored if r.solved]
        return round(mean(solved), 2) if solved else 0.0

    def by_difficulty(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for d in ("easy", "medium", "hard"):
            rows = [r for r in self.scored if r.difficulty == d]
            if rows:
                out[d] = {"n": len(rows),
                          "solve_rate": round(sum(1 for r in rows if r.solved) / len(rows), 4)}
        return out

    def summary(self) -> dict:
        return {
            "n_tasks": len(self.results),
            "n_scored": len(self.scored),
            "n_harness_errors": len(self.results) - len(self.scored),
            "pass_at_1": self.pass_at_1,
            "solve_rate": self.solve_rate,
            "recovery_rate": self.recovery_rate,
            "escalation_rate": self.escalation_rate,
            "mean_attempts_to_solve": self.mean_attempts_to_solve,
            "by_difficulty": self.by_difficulty(),
        }

    def to_dict(self) -> dict:
        return {"summary": self.summary(), "results": [asdict(r) for r in self.results]}

    def render(self) -> str:
        s = self.summary()
        lines = [
            "",
            "=" * 62,
            "  Coding Engineer -- execution-based eval",
            "=" * 62,
            f"  tasks scored          {s['n_scored']}/{s['n_tasks']}"
            + (f"  ({s['n_harness_errors']} harness error(s) excluded)" if s["n_harness_errors"] else ""),
            "",
            f"  Pass@1                {s['pass_at_1']:.2%}",
            f"  Solve rate (Pass@k)   {s['solve_rate']:.2%}",
            f"  Recovery rate         {s['recovery_rate']:.2%}   (of tasks that failed attempt 1)",
            f"  Escalation rate       {s['escalation_rate']:.2%}",
            f"  Mean attempts/solve   {s['mean_attempts_to_solve']}",
            "",
            "  by difficulty:",
        ]
        for d, v in s["by_difficulty"].items():
            lines.append(f"    {d:8s} n={v['n']}  solve={v['solve_rate']:.2%}")
        lines += ["", "  per task:"]
        for r in self.results:
            if not r.valid:
                mark = "ERR "
            elif r.solved:
                mark = "PASS"
            else:
                mark = "FAIL"
            lines.append(
                f"    [{mark}] {r.task_id:10s} {r.difficulty:6s} "
                f"attempts={r.attempts:<3d} {r.wall_clock_s:6.1f}s"
                + (f"  {r.error}" if r.error else "")
            )
        lines.append("=" * 62)
        return "\n".join(lines)
