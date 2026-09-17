"""FastAPI wrapper around the Coding Engineer agent.

    uv run uvicorn api.main:app --reload --port 8009
    # then open http://127.0.0.1:8009/docs

Typical Swagger flow:
  1. GET  /folders/roots      -- where to start browsing
  2. GET  /folders?path=...   -- walk to the repo you want, note `path`
  3. GET  /models             -- confirm which models will be used
  4. POST /runs               -- paste that path + a goal
  5. GET  /runs/{id}          -- poll; then /report and /diff when finished
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from api import folders, schemas, settings
from api.runner import REGISTRY, Run

app = FastAPI(
    title="Coding Engineer API",
    version="0.1.0",
    description=(
        "Point the Coding Engineer agent at a local folder and give it a goal.\n\n"
        "**The agent branches a git worktree off the target's HEAD.** Two consequences worth "
        "knowing before your first run:\n\n"
        "- Uncommitted changes in the target are *invisible* to the agent.\n"
        "- **Your target folder is never written to.** Output appears in a worktree under the "
        "*agent repo's* `.loop/worktrees/<run_id>/`, on branch `coding-engineer/<run_id>`. "
        "A target folder that stays empty is the design working, not a failure — "
        "`GET /runs/{id}` reports `worktree_dir`.\n\n"
        f"Target folders allowed: `{settings.roots_description()}`.\n\n"
        "One run executes at a time; a second POST /runs returns 409 while one is active."
    ),
)


# ---------------------------------------------------------------- meta -------
@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "active_run": REGISTRY.active_id(),
            "allowed_roots": settings.roots_description()}


@app.get("/models", response_model=schemas.ModelInfo, tags=["meta"],
         summary="Which models a run would use right now")
def models() -> schemas.ModelInfo:
    from coding_agent.models import describe_all
    info = describe_all()
    return schemas.ModelInfo(primary=info["primary"], secondary=info["secondary"])


# ------------------------------------------------------------- folders -------
@app.get("/folders/roots", response_model=list[str], tags=["folders"],
         summary="Starting points for browsing")
def folder_roots() -> list[str]:
    return folders.roots()


@app.get("/folders", response_model=schemas.FolderListing, tags=["folders"],
         summary="Browse a folder and check whether it is a usable target")
def browse(
    path: str = Query(..., description="Absolute path to list.", examples=["H:/code/yl"]),
    include_hidden: bool = Query(False, description="Include dot-directories."),
) -> schemas.FolderListing:
    p = folders.require_dir(path)
    root = folders.git_root(p)
    return schemas.FolderListing(
        path=str(p),
        parent=str(p.parent) if p.parent != p else None,
        is_git_repo=root is not None,
        git_root=str(root) if root else None,
        uncommitted=folders.dirty_files(p) if root else [],
        entries=[schemas.FolderEntry(**e) for e in folders.list_children(p, include_hidden)],
    )


# ---------------------------------------------------------------- runs -------
def _summary(r: Run) -> dict:
    return {"run_id": r.run_id, "status": r.status, "goal": r.goal,
            "target_dir": r.target_dir, "started_at": r.started_at,
            "finished_at": r.finished_at, "duration_s": r.duration_s,
            "event_count": len(r.events), "error": r.error}


def _require(run_id: str) -> Run:
    run = REGISTRY.get(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run: {run_id}")
    return run


@app.post("/runs", response_model=schemas.StartRunResponse, status_code=202, tags=["runs"],
          summary="Start a run against a local folder")
def start_run(req: schemas.StartRunRequest) -> schemas.StartRunResponse:
    target = folders.require_dir(req.target_dir)
    if folders.git_root(target) is None:
        raise HTTPException(
            400,
            f"{target} is not inside a git repo. The agent branches a worktree off HEAD; "
            "without a repo it silently falls back to copying, which makes the result hard "
            "to review. Run `git init` there, or pick another folder.",
        )
    try:
        run = REGISTRY.start(
            goal=req.goal.strip(),
            target_dir=str(target),
            budgets=req.budgets.model_dump() if req.budgets else None,
            primary_model=req.primary_model,
            secondary_model=req.secondary_model,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return schemas.StartRunResponse(
        run_id=run.run_id, status=run.status, target_dir=run.target_dir,
        goal=run.goal, poll=f"/runs/{run.run_id}",
        note=(
            f"{target} is NOT modified. The agent works in a git worktree on branch "
            f"coding-engineer/{run.run_id}, created under the agent repo's .loop/worktrees/. "
            f"GET /runs/{run.run_id} reports worktree_dir as soon as intake finishes — "
            "that is where the files appear."
        ),
    )


@app.get("/runs", response_model=list[schemas.RunSummary], tags=["runs"])
def list_runs() -> list[dict]:
    return [_summary(r) for r in REGISTRY.list()]


@app.get("/runs/{run_id}", response_model=schemas.RunDetail, tags=["runs"],
         summary="Status, outcome and the node trace")
def get_run(run_id: str, events: bool = Query(True, description="Include the per-node trace.")) -> dict:
    run = _require(run_id)
    state = run.final_state
    changed = [f for f in (state.get("last_diff") or "").splitlines()
               if f.startswith("+++ b/")]
    detail = _summary(run) | {
        "outcome": state.get("outcome") or state.get("status"),
        "escalation_reason": state.get("escalation_reason"),
        "attempts": state.get("total_attempts"),
        "worktree_dir": state.get("worktree_dir"),
        "branch": state.get("branch"),
        "changed_files": [f[len("+++ b/"):] for f in changed],
        "report_path": str(report) if (report := _report_path(run_id)) and report.exists() else None,
        "events": run.events if events else [],
    }
    return detail


def _report_path(run_id: str) -> Path | None:
    """Where the engine writes the run report, or None if the agent package is
    not importable. A broken agent environment should degrade this endpoint,
    not turn every status poll into a 500."""
    try:
        from coding_agent.nodes import _loop_state_dir
    except Exception:  # noqa: BLE001 -- any import failure means "no report path"
        return None
    return _loop_state_dir() / "state" / "coding-engineer" / run_id / "run-report.md"


@app.get("/runs/{run_id}/report", response_class=PlainTextResponse, tags=["runs"],
         summary="The run report (markdown)")
def get_report(run_id: str) -> str:
    _require(run_id)
    path = _report_path(run_id)
    if path is None or not path.exists():
        raise HTTPException(404, "no report yet — the engine writes it when the run ends")
    return path.read_text(encoding="utf-8")


@app.get("/runs/{run_id}/diff", response_class=PlainTextResponse, tags=["runs"],
         summary="The diff the agent produced in its worktree")
def get_diff(run_id: str) -> str:
    run = _require(run_id)
    diff = run.final_state.get("last_diff")
    if not diff:
        raise HTTPException(404, "no diff recorded yet")
    return diff


@app.post("/runs/{run_id}/stop", tags=["runs"],
          summary="Ask a running run to stop at its next checkpoint")
def stop_run(run_id: str) -> dict:
    run = _require(run_id)
    if run.status not in ("running", "stopping"):
        raise HTTPException(409, f"run is {run.status}, not running")
    path = REGISTRY.request_stop(run_id)
    return {"run_id": run_id, "status": "stopping", "stop_flag": str(path),
            "note": "the engine checks this between attempts; it does not kill mid-write"}


@app.delete("/runs/{run_id}", status_code=204, tags=["runs"],
            summary="Forget a finished run (does not touch its worktree)")
def forget_run(run_id: str) -> None:
    _require(run_id)
    if not REGISTRY.forget(run_id):
        raise HTTPException(409, "cannot forget the active run — stop it first")


def main() -> None:
    import uvicorn
    uvicorn.run("api.main:app", host=settings.HOST, port=settings.PORT, reload=False)


if __name__ == "__main__":
    main()
