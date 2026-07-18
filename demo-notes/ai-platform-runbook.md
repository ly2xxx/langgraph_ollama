---
description: Operations runbook for the local AI platform (Ollama, LangGraph agents, LGTM observability)
---

# AI Platform Runbook

Operational knowledge for the local-first AI stack: Ollama model serving,
LangGraph agents, md-mcp knowledge server, and the LGTM observability stack.

## Architecture overview

The platform has three layers:

1. **Serving** — Ollama hosts all models locally (chat + embeddings). No
   cloud API calls; data never leaves the machine.
2. **Orchestration** — LangGraph agents (RAG chatbot, article writer,
   internet researcher) coordinate LLM calls, tools, and memory.
3. **Observability** — OpenTelemetry exports traces to Tempo, metrics to
   Prometheus, and logs to Loki, all visualized in Grafana. One trace ID
   follows a request from the Streamlit click through the agent graph and
   across the MCP boundary into the md-mcp tool server.

## Incident response

### Symptom: agent answers are slow

1. Open the Grafana dashboard and check the latency percentile panel.
2. If p95 is dominated by token generation, check Ollama GPU utilisation.
3. If a single node dominates, open the request trace in Tempo — each graph
   node and LLM call is its own span with token counts attached.

### Symptom: retrieval quality dropped

1. Check whether the md-mcp file watcher invalidated its cache recently
   (log line "Cache invalidated" in Loki).
2. Run the `rescan_folder` MCP tool to force a fresh index.
3. Verify chunking: sections over 1000 characters are split by paragraph,
   which can separate a heading from its table. Restructure the note if so.

## Deployment checklist

- Pull models before the demo: `ollama pull nomic-embed-text`
- Start the stack: `.\demo.ps1` (pre-flight checks + LGTM + app)
- Verify one end-to-end trace in Tempo before going live
- Grafana admin password is rotated quarterly (see security note)

## SLOs

| Signal | Target |
|---|---|
| RAG answer p95 latency | < 30 s local CPU, < 8 s GPU |
| Retrieval tool call p95 | < 500 ms |
| Trace export loss | < 1 % |
