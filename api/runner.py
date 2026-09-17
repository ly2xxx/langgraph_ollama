"""Background execution of Coding Engineer runs, with an in-memory registry.

engine.stream_run is a blocking generator, so each run gets a daemon thread and
the endpoints read a snapshot under a lock.

Only one run executes at a time, deliberately. Per-run model overrides are
applied through environment variables (get_llm reads env at call time, which is
how the Streamlit panel does it too), and the environment is process-global --
two concurrent runs with different overrides would silently read each other's
models. Serialising is honest; a queue that hides the contention is not.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api import settings


@dataclass
class Run:
    run_id: str
    goal: str
    target_dir: str
    started_at: float
    status: str = "running"
    finished_at: float | None = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float | None:
        if self.finished_at is None:
            return None
        return round(self.finished_at - self.started_at, 1)


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}
        self._active: str | None = None

    # ---- queries -----------------------------------------------------------
    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[Run]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)

    def active_id(self) -> str | None:
        with self._lock:
            return self._active

    def forget(self, run_id: str) -> bool:
        with self._lock:
            if run_id == self._active:
                return False
            return self._runs.pop(run_id, None) is not None

    # ---- execution ---------------------------------------------------------
    def start(self, *, goal: str, target_dir: str, budgets: dict | None,
              primary_model: str | None, secondary_model: str | None) -> Run:
        from coding_agent.engine import new_run_id

        with self._lock:
            if self._active is not None:
                raise RuntimeError(f"a run is already in progress: {self._active}")
            run_id = new_run_id()
            run = Run(run_id=run_id, goal=goal, target_dir=target_dir, started_at=time.time())
            self._runs[run_id] = run
            self._active = run_id
            self._evict_locked()

        threading.Thread(
            target=self._execute,
            args=(run, budgets, primary_model, secondary_model),
            name=f"coding-engineer-{run_id}",
            daemon=True,
        ).start()
        return run

    def _evict_locked(self) -> None:
        finished = [r for r in self._runs.values() if r.status != "running" and r.run_id != self._active]
        excess = len(self._runs) - settings.MAX_REMEMBERED_RUNS
        for r in sorted(finished, key=lambda r: r.started_at)[:max(0, excess)]:
            self._runs.pop(r.run_id, None)

    def _execute(self, run: Run, budgets: dict | None,
                 primary_model: str | None, secondary_model: str | None) -> None:
        from coding_agent.engine import stream_run

        previous_env = {}
        try:
            for var, value in (("CODING_AGENT_PRIMARY_MODEL", primary_model),
                               ("CODING_AGENT_SECONDARY_MODEL", secondary_model)):
                if value:
                    previous_env[var] = os.environ.get(var)
                    os.environ[var] = value

            seq = 0
            for update in stream_run(run.run_id, run.target_dir, run.goal,
                                     hitl=False, budgets=budgets or None):
                for node_name, node_update in update.items():
                    seq += 1
                    if node_name == "__interrupt__":
                        self._append(run, seq, node_name, None, str(node_update)[:500])
                        continue
                    if not isinstance(node_update, dict):
                        self._append(run, seq, node_name, None, None)
                        continue
                    messages = node_update.get("messages") or []
                    note = getattr(messages[-1], "content", None) if messages else None
                    self._append(run, seq, node_name, node_update.get("status"),
                                 str(note)[:500] if note else None)
                    with self._lock:
                        run.final_state.update(node_update)

            status = str(run.final_state.get("status") or "done")
            with self._lock:
                run.status = "escalated" if status == "escalated" else "done"
        except Exception:
            with self._lock:
                run.status = "failed"
                run.error = traceback.format_exc(limit=8)
        finally:
            for var, old in previous_env.items():
                if old is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = old
            with self._lock:
                run.finished_at = time.time()
                if self._active == run.run_id:
                    self._active = None

    def _append(self, run: Run, seq: int, node: str, status: str | None, note: str | None) -> None:
        with self._lock:
            run.events.append({"seq": seq, "node": node, "status": status,
                               "note": note, "at": time.time()})

    # ---- cooperative stop --------------------------------------------------
    def request_stop(self, run_id: str) -> Path:
        """Raise the engine's stop flag; diagnose checks it between attempts, so
        the run ends at the next checkpoint rather than being killed mid-write."""
        from coding_agent.nodes import _loop_state_dir
        from coding_agent.report import stop_flag_path

        path = stop_flag_path(run_id, _loop_state_dir())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stop", encoding="utf-8")
        with self._lock:
            run = self._runs.get(run_id)
            if run and run.status == "running":
                run.status = "stopping"
        return path


REGISTRY = RunRegistry()
