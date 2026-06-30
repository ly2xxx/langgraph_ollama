# Demo Guide — langgraph_ollama

> **Interview angle: the heavyweight "production AI engineering" piece.**
> RAG + agent orchestration + production observability. This is the project that
> proves you build *production-grade* AI systems, not notebook prototypes.

## JD skills this project demonstrates

| JD essential skill                                         | Where it lives                                                                                       |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| RAG                                                        | `rag_research_chatbot.py`, `tools/rag.py`, `web_researcher.py`                                 |
| AI agent frameworks & orchestration                        | LangGraph multi-agent (`mm_agent.py`, `app.py`)                                                  |
| Embeddings / vector search                                 | `nomic-embed-text` embedding pipeline for RAG                                                      |
| Prompt engineering                                         | `web_research_prompts.py`                                                                          |
| Model serving                                              | Ollama local serving (`OLLAMA_MODEL`, `OLLAMA_BASE_URL`)                                         |
| **Observability / monitoring** (lead responsibility) | OpenTelemetry`telemetry.py` + `observability/` stack: OTEL collector, Prometheus, Grafana, Tempo |
| Python                                                     | whole project                                                                                        |

## Demo flow (≈5 min)

```bash
# 0. Prereqs: Ollama running + embedding model pulled
ollama pull nomic-embed-text

# 1. Launch the app
uv sync --extra observability
uv run streamlit run app.py

2. (Optional but high-impact) bring up the observability stack
docker compose -f docker-compose.observability.yml down
docker compose -f docker-compose.observability.yml up -d
#    -> Grafana dashboards under observability/grafana
```

**Run a RAG query in the UI, then switch to Grafana** to show spans, token
counts, and latency lighting up in real time.

"What is the order of SQL query execution of SELECT, FROM, GROUP BY, HAVING, ORDER BY, LIMIT, OFFSET ?"

## Talking points (Lead / Architect framing)

- **"I instrument AI systems like production services."** OpenInference auto-
  instruments every LangGraph node + LLM call; custom Prometheus metrics
  (request count, latency, tokens) feed Grafana panels. Tracing goes to Tempo.
- **Graceful degradation by design** — `telemetry.py` is idempotent and never
  breaks the app if the collector is down or OTEL isn't installed.
- **Cost & latency awareness** — token counts and latency are first-class
  signals, directly matching the JD's "optimize for latency, cost, accuracy."
- **Local model serving** keeps data on-prem — ties into "secure AI solution
  design" and "data handled responsibly."


If have time: [127.0.0.1:18789](http://127.0.0.1:18789/)

[www.linkedin.com/in/yang-li-78917021](https://www.linkedin.com/in/yang-li-78917021)

[github.com/ly2xxx/openclaw-control-panel/blob/main/maintenance/install-openclaw.ps1](https://github.com/ly2xxx/openclaw-control-panel/blob/main/maintenance/install-openclaw.ps1)

## The one-liner

> "RAG and multi-agent orchestration with full OpenTelemetry observability —
> Prometheus, Grafana, and Tempo — so reliability and cost are measurable, not
> assumed."

