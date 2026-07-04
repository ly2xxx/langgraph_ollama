# Changelist — July 2026 fixes & features

One commit per entry. Each entry is updated with a description of the actual
code change when it lands.

## Planned

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
