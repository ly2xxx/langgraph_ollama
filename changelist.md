# Changelist — July 2026 fixes & features

One commit per entry. Each entry is updated with a description of the actual
code change when it lands.

## Planned

- [ ] **Fix: `tools/rag.py` hardcoded Ollama URL** — embeddings ignore
  `OLLAMA_BASE_URL` and always hit `http://localhost:11434`.
- [ ] **Perf: cache FAISS index per file** — `rag_query` re-embeds the whole
  document on every call; cache the index keyed by file content hash.
- [ ] **Observability: cover all agents** — `track_request()` + token metrics
  currently wrap only the Internet Researcher; extend to RAG Chatbot and
  Article Writer.
- [ ] **Cleanup: SqliteSaver monkeypatch + hardcoded paths** — replace the
  `from_conn_stringx` classmethod hack in `mm_agent.py` with the supported
  constructor; parameterize `D:\code\...` paths in `__main__` test blocks.
- [ ] **Feature: md-mcp as a retrieval tool source** — optionally load MCP
  tools (search_markdown etc.) from a running md-mcp server via
  `langchain-mcp-adapters`, configured with `MD_MCP_URL`; agents gain a
  markdown knowledge-base tool with zero local indexing.

## Done

- [x] **Fix: stop tracking `.env`** — `git rm --cached .env` (file stays on
  disk, git stops tracking it; `.gitignore` already listed it but ignore rules
  don't apply to tracked files). Added `.env.example` with placeholder values
  as the committed template. Prevents a real `TAVILY_API_KEY` from ever being
  committed by `git commit -a`.
