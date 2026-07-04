# Changelist — July 2026 fixes & features

One commit per entry. Each entry is updated with a description of the actual
code change when it lands.

## Planned


## Done

- [x] **Feature: distributed tracing across the MCP boundary** — the agent's
  trace now continues into md-mcp instead of the two services emitting
  separate traces. Client side: `telemetry.py` instruments httpx
  (`opentelemetry-instrumentation-httpx`, added to the observability extra)
  so outbound MCP requests carry the active span's W3C `traceparent` header.
  Server side (md-mcp repo): the FastMCP middleware extracts `traceparent`
  from the incoming HTTP request and parents its spans to it. Also fixed a
  Windows bug where the non-ASCII `→` in the "OTEL active" print raised
  UnicodeEncodeError on cp1252 consoles and made init report failure.
  Verified in Tempo: a single trace ID contains `agent.run` +
  `search_markdown` spans from `langgraph-ollama` and
  `mcp.tool/search_markdown` + `mcp.request/*` spans from `md-mcp`.

- [x] **Feature: md-mcp as a retrieval tool source** — new
  `tools/mcp_notes.py` connects to a running md-mcp server via
  `langchain-mcp-adapters` (pinned `>=0.1.9,<0.2`; the 0.2 line requires a
  newer langchain-core than our 0.3.x stack) and exposes its MCP tools
  (`search_markdown`, `list_files`, `rescan_folder`) as sync-wrapped
  LangChain tools. Enabled by setting `MD_MCP_URL` (see `.env.example`);
  unset or unreachable degrades to `[]` with a 60s negative-cache, so the app
  runs unchanged without it. `rag_research_chatbot.local_rag` now appends
  these tools to the RAG agent's toolset. Verified live against
  `md-mcp:local` in Docker: all 3 tools discovered and callable synchronously.

- [x] **Cleanup: SqliteSaver monkeypatch + hardcoded paths** — `mm_agent.py`
  now constructs `SqliteSaver(conn=sqlite3.connect(":memory:",
  check_same_thread=False))` directly instead of monkeypatching a
  `from_conn_stringx` classmethod onto the class (supported since
  langgraph-checkpoint-sqlite 2.x). The `D:\code\langgraph_agents\...` paths
  in the `__main__` blocks of `tools/rag.py` and `rag_research_chatbot.py`
  were replaced with a `RAG_TEST_FILE` env var (plus `RAG_TEST_QUERY`), which
  also removes the `SyntaxWarning: invalid escape sequence` noise on import.

- [x] **Observability: cover all agents** — Article Writer graph runs
  (`mm_agent.py` `start()`/`resume()`) are now wrapped in
  `telemetry.track_request("Article Writer", ...)`, covering both the app.py
  and mm_st.py entry paths. Internet Researcher now also records per-node
  token metrics in the stream loop (`app.py`) via
  `extract_token_usage`/`record_tokens`. (RAG Chatbot was already fully
  instrumented in `run_chatbot_graph`.)

- [x] **Perf: cache FAISS index per file** — `tools/rag.py` now keeps an
  in-process index cache keyed by `(file path, sha256 of file bytes, embed
  model)` with a small size bound. Unchanged files skip re-embedding entirely
  (previously every `rag_query` call re-embedded the whole document through
  Ollama); editing the file invalidates the entry via the content hash.
  Verified with FakeEmbeddings: cache hit on repeat query, rebuild on edit.

- [x] **Fix: `tools/rag.py` hardcoded Ollama URL** — `OllamaEmbeddings` now
  reads `OLLAMA_BASE_URL` (falling back to `http://localhost:11434`) so
  embeddings follow the same server as the chat model. Embedding model is also
  configurable via new `OLLAMA_EMBED_MODEL` env (default `nomic-embed-text`).

- [x] **Fix: stop tracking `.env`** — `git rm --cached .env` (file stays on
  disk, git stops tracking it; `.gitignore` already listed it but ignore rules
  don't apply to tracked files). Added `.env.example` with placeholder values
  as the committed template. Prevents a real `TAVILY_API_KEY` from ever being
  committed by `git commit -a`.
