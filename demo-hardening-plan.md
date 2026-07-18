# Interview Demo Hardening Plan

Goal: make the combined md-mcp + langgraph_ollama demo reliably runnable in
under 30 minutes, with zero dead air and no fragile manual setup. Companion to
[demo.md](demo.md) (the talk track); this file tracks the engineering work.

## Item 1 — One-command launcher + pre-flight check ✅

- [x] `demo.ps1` in repo root:
  - [x] Pre-flight: Docker engine up (auto-start Docker Desktop if not; 6 min
        cold-start allowance), Ollama reachable, required models pulled
        (`OLLAMA_MODEL`, `nomic-embed-text`), md-mcp image present (pull if
        missing)
  - [x] Start LGTM observability stack (`docker compose ... up -d`), wait for
        Grafana + Loki + collector health
  - [x] Start Streamlit app (skip if port 8501 already serving), wait for ready
  - [x] Open browser tabs: app + Grafana dashboard (`-NoBrowser` to skip)
  - [x] Clear PASS/FAIL summary with fix instructions on any failure
- [x] Verified end-to-end on this machine (incl. the failure path: Docker
      cold-start timeout correctly reported FAIL with fix instructions)

## Item 2 — Kill the app startup latency ✅

- [x] Remove module-level graph build in `rag_research_chatbot.py` (a full
      chatbot graph is compiled at import time and thrown away)
- [x] Build only the selected agent's graph in `app.py` via `build_chain()`
      (previously all three were constructed on every Streamlit rerun)
- [x] Cache graph construction with `st.cache_resource`
- [x] Cache the mermaid graph PNG to disk under `.cache/graph-png/` keyed by
      mermaid source hash; graceful fallback shows the mermaid source text if
      mermaid.ink is unreachable
- [x] Verified live: agent switch builds + renders in ~2s, PNGs served from
      disk on every subsequent rerun (no network). First process start still
      pays ~1-2 min of langchain imports — pre-warm by launching the app
      before the interview (demo.ps1 does this).

## Item 3 — Demo mode (determinism) ✅

- [x] `demo-notes/` folder in-repo (runbook, SQL execution order, context
      engineering) — canned queries hit them deterministically
- [x] `.env.demo` preset + `-Demo` switch in `demo.ps1` (backs up `.env`,
      preserves a real Tavily key)
- [x] Canned demo queries dropdown in the app (RAG + Researcher agents)
- [x] Verified: canned SQL query answered from demo-notes via md-mcp
      ("Found note – Logical execution order of a SQL SELECT query").
      Required fixing a real md-mcp bug: keyword search demanded the whole
      query as an exact substring, so natural-language questions returned
      nothing. Fixed in md-mcp `chunking.py`, image rebuilt locally.
- [x] Bonus: model switched to `gpt-oss:120b-cloud` (glm-5:cloud retired
      server-side with 410); pre-flight now does a live generation test
- [x] Bonus: md-mcp now long-lived HTTP container (`MD_MCP_URL`) — query time
      127s → ~60s (no more per-call `docker run`)

## Item 4 — Pre-set "interview" Grafana dashboard ✅

- [x] Dashboard defaults: last 15 minutes, 5s auto-refresh
- [x] "Recent traces" panel (Tempo TraceQL search) — zero typing live
- [x] Traces + logs panels side by side directly under the stat row
- [x] Verified: request traces (58-span LangGraph waterfall) in Tempo, logs
      with trace_id in Loki, dashboard reloaded with new layout
- [ ] OUTSTANDING: confirm md-mcp spans appear INSIDE the agent trace (the
      OpenInference→OTel context bridge in tools/mcp_notes.py was the last
      change; run one RAG query and open the newest LangGraph trace) — see
      demo-changes-2026-07-18.md §4
