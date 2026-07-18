# Demo Hardening — What Changed (2026-07-18)

Study guide for all changes made across `langgraph_ollama` and `md-mcp` while
implementing Items 1–4 of [demo-hardening-plan.md](demo-hardening-plan.md).
Everything below is in the working tree, uncommitted — review and commit when
happy.

---

## TL;DR

- `.\demo.ps1` now launches the whole demo in one command with pre-flight checks.
- `glm-5:cloud` **was retired by Ollama cloud (410 Gone)** — everything now uses
  its successor `glm-5.2:cloud` (chat + tool-calling verified; user's choice).
- Found and fixed a real md-mcp bug: keyword search required the whole query as
  an exact substring, so natural-language questions from the LLM returned
  nothing. Local Docker image rebuilt with the fix (not pushed to Docker Hub).
- md-mcp now runs as a long-lived HTTP container in the demo (was: a fresh
  `docker run` per tool call — ~10s each; a query went 127s → ~60s).
- App startup latency cut: only the selected agent's graph is built (cached),
  graph PNGs cached on disk (mermaid.ink no longer hit per rerun).
- Demo mode: `demo-notes/` content, `.env.demo` preset, canned-query dropdown.
- Grafana dashboard: 15-min window, 5s refresh, "Recent traces" + logs panels
  in a prominent row.

---

## 1. langgraph_ollama repo

### demo.ps1 (new) — one-command launcher
- Pre-flight: `.env` sanity, Docker engine (auto-starts Docker Desktop, waits
  up to 6 min for cold start), Ollama reachable, models present, **plus a live
  1-token generation test** — because a cloud-routed model can be retired
  server-side and still *list* as installed (exactly how glm-5:cloud died).
- Starts the LGTM stack and health-gates on Grafana `/api/health` + Loki `/ready`.
- Starts a persistent `md-mcp-demo` container (HTTP transport, notes folder
  mounted read-only, OTel exported to the collector via `host.docker.internal`).
- Starts Streamlit (skips if port 8501 already serving), opens browser tabs.
- Flags: `-Demo` (apply `.env.demo`, backs up `.env` and preserves a real
  Tavily key), `-ChecksOnly`, `-NoBrowser`.

### app.py
- `build_chain()` with `@st.cache_resource`: builds ONLY the selected agent's
  graph, once per (agent, model). Previously all three agents were constructed
  on every Streamlit rerun. (Safe for Article Writer: `mm_st.py` keeps its own
  checkpointed instance in session state; app.py's copy is only for the picture.)
- `displayGraph()`: mermaid PNG now cached in `.cache/graph-png/` keyed by the
  graph's mermaid source hash. `draw_mermaid_png()` calls the remote mermaid.ink
  service — previously on *every rerun*, now at most once per graph shape, with
  a graceful fallback (shows mermaid source) if offline.
- `DEMO_QUERIES` dropdown per agent — selecting one pre-fills the query box.
  Queries are phrased to route reliably to the md-mcp tools.
- Chat answer extraction: takes the last message *with content* instead of
  `messages[-1]` — after the summarize node prunes history on turn 2+, the last
  message can be empty (this made the second answer render blank).
- Sidebar MCP status now distinguishes `MD_MCP_URL` (http) vs `MD_MCP_FOLDER`
  (stdio) modes.

### rag_research_chatbot.py
- Removed module-level `RAGResearchChatbot()` + graph compile — a full graph
  was built at *import time* and thrown away on every process start.

### tools/mcp_notes.py
- New preferred mode `MD_MCP_URL` (streamable-http to a long-lived server);
  `MD_MCP_FOLDER` stdio-docker-spawn kept as fallback. HTTP mode is faster
  (no per-session `docker run`) and observable.
- **Trace-context bridge** in `_sync_wrap`: OpenInference builds its span tree
  from LangChain callbacks without attaching OTel runtime context, so outbound
  HTTP inside a tool started a *new root trace* — md-mcp's spans landed in a
  separate trace. The wrapper now looks up the tool run's OpenInference span
  (via the callback manager's `parent_run_id` → `LangChainInstrumentor().get_span()`)
  and attaches it as OTel context for exactly the duration of the MCP call, so
  httpx's `traceparent` header carries the agent trace into md-mcp.
  **Status: bridge implemented; final end-to-end confirmation of md-mcp spans
  inside the agent trace was still in flight when work stopped — check the
  newest LangGraph trace in Tempo after one RAG query.**

### Config
- `.env` / `.env.example` / `README.md`: model → `gpt-oss:120b-cloud`.
- `.env.demo` (new, committed, no secrets): demo model, `MD_MCP_FOLDER` →
  `demo-notes/`, `MD_MCP_URL=http://localhost:8000/mcp`, OTLP endpoint.
- `.claude/launch.json` (new): dev-server config for the Streamlit app.

### demo-notes/ (new)
Three curated notes the canned queries hit deterministically:
- `ai-platform-runbook.md` — architecture, incident response, SLOs.
- `sql-execution-order.md` — the SQL SELECT logical execution order.
- `context-engineering.md` — the md-mcp design thesis (good talking points).

### Grafana ([observability/grafana/dashboards/langgraph-ollama.json](observability/grafana/dashboards/langgraph-ollama.json))
- Defaults: last 15 minutes, 5s auto-refresh (no fiddling on stage).
- New "Recent traces" panel (Tempo TraceQL search, click a trace ID to open
  the waterfall) side by side with the live Loki logs panel, directly under
  the stat row — the money-shot row needs zero typing during the demo.

---

## 2. md-mcp repo

### md_mcp/chunking.py — natural-language search fix (the big one)
`search_chunks` (default `"keyword"` strategy of the `search_markdown` MCP
tool) only returned chunks containing the ENTIRE query as an exact substring:

```python
if query_lower in chunk.content.lower():   # old gate
```

An LLM calls it with questions like *"what is the logical execution order of a
SQL SELECT query?"* — never a verbatim substring — so it returned **0 results**
against notes that plainly contained the answer (repro confirmed). Fixed:

- New `_query_terms()`: lowercases, strips stopwords ("what is the of a...").
- `search_chunks`: matches on exact phrase OR any content-bearing term, ranked
  by `calculate_relevance`.
- `calculate_relevance`: exact-phrase bonuses still rank verbatim matches on
  top (+3 content / +2 header); per-term frequency scoring (capped per term so
  one repeated word can't dominate).
- `extract_snippet`: anchors on the line with the most query terms instead of
  falling back to the first 5 lines.

Verified: all three demo canned queries now return the right note with the
right section top-ranked; existing test scripts pass (`test_chunking.py`,
`test_chunking_simple.py`).

### Docker image
Rebuilt `ly2xxx/md-mcp:latest` **locally** with the fix (OTel packages baked
in by default via `INSTALL_OBSERVABILITY=true`). **Not pushed to Docker Hub —
your call.** Also consider a version bump + PyPI release since the search fix
affects the published package.

---

## 3. Things verified working end-to-end today

- `demo.ps1` full run: pre-flight (incl. catching the retired model), stack
  health gates, md-mcp HTTP container, app start, correct URLs printed.
- RAG query → md-mcp `search_markdown`/`read_file` over streamable-http →
  answer opens with "**Found note – Logical execution order of a SQL SELECT
  query**" (retrieval hit, not parametric knowledge).
- Traces: root `LangGraph` trace with 58 spans (nodes, LLM calls, tool calls)
  in Tempo; earlier "no traces" scare was a search-timing artifact, tracing
  worked all along. md-mcp server-side spans confirmed exporting and parenting
  to the caller's httpx span.
- Logs: app logs (incl. inside-run lines) land in Loki with `trace_id`
  correlation; dashboard logs panel shows them.
- Grafana provisioning reloads: datasources (Prom/Tempo/Loki + cross-links)
  and the reworked dashboard.

## 4. Open items / for tomorrow

1. **Confirm the single distributed trace**: run one RAG canned query, open
   the newest `LangGraph` trace in Grafana → Tempo, and check it now contains
   `md-mcp` `mcp.tool/...` spans (the context bridge above). If they still
   appear as separate traces, look at `tools/mcp_notes.py::_openinference_span_context`.
2. Decide on publishing: `docker push ly2xxx/md-mcp:latest` + PyPI 1.0.6 with
   the search fix (and a CHANGELOG entry).
3. `git add` + commit both repos (nothing committed today).
4. Optional next demo items (not started): one-command deepeval scorecard
   (`sample-client/`), combined architecture diagram for the READMEs, kind/
   Helm live deploy, 2-min backup screen recording.

## 5. Demo-day quick reference

```powershell
.\demo.ps1 -Demo          # full stack + demo preset
# App     : http://localhost:8501       (canned queries in the dropdown)
# Grafana : http://localhost:3001/d/cfr1bvchmx4owb/?from=now-15m&to=now&refresh=5s
#           (admin/admin; traces + logs panels are the second row)
```

First page load pays ~1.5 min of Python imports — start the app before the
interview; every interaction after that is fast.
