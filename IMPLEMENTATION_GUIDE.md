# Observability Showcase — Implementation & Study Guide

Adding **OpenTelemetry → Prometheus + Grafana + Tempo** to the LangGraph + Ollama
Streamlit app. This guide explains *what* was added, *why* each piece exists, and
*how* to run, demo, and extend it — so you can learn the stack, not just copy it.

> Stack context: this is the **2026-modernized** project — LangChain/LangGraph
> **0.3.x**, the `langchain-ollama` partner package, **Python 3.12**, and **uv**
> packaging. The OTEL deps live in a `pyproject.toml` optional group, not a
> `requirements.txt`.

---

## 1. The mental model (read this first)

There are three kinds of telemetry, and people constantly confuse them:

| Signal            | Question it answers                                   | Backend here | Example                                                            |
| ----------------- | ----------------------------------------------------- | ------------ | ------------------------------------------------------------------ |
| **Metrics** | "How much / how fast, aggregated over time?"          | Prometheus   | p95 latency, requests/sec, tokens/sec                              |
| **Traces**  | "What happened in*this one* request, step by step?" | Tempo        | This query spent 4.2s in the`rag` node, 1.1s in `conversation` |
| **Logs**    | "What did the code say while it happened?"            | Loki         | "FAISS index cache hit for report.pdf" — linked to its trace     |

**OpenTelemetry (OTEL)** is the vendor-neutral *plumbing* that produces all
three. Your app emits OTEL data once; the **Collector** routes metrics to
Prometheus, traces to Tempo, and logs to Loki. **Grafana** is the single UI
that reads all of them.

```
                                  ┌── traces ──►  Tempo  ◄────┐
  Streamlit app  ──OTLP:4317──►  Collector ── metrics ─►  Prometheus ──►  Grafana :3000
  (telemetry.py)                  └── logs ───►  Loki  ◄─────┘
                                     (Prometheus scrapes collector :8889)
```

Why a Collector in the middle instead of exporting straight to each backend?
Because the app should only ever know *one* protocol (OTLP). Want to swap Tempo
for Jaeger, or add a cloud backend? You edit the Collector config, never the app.
That decoupling is the whole point of OTEL and the most important idea to take
away.

---

## 2. Why this app is a good showcase

LLM agent apps surface signals that are genuinely interesting to observe — unlike
a CRUD app where every request looks the same. This project has **three** agents,
all of which flow through `langchain_ollama.ChatOllama`:

- **RAG Chatbot** — retrieval (`rag` node) → `conversation` → `summarize`.
- **Article Writer** — a LangGraph writer/critique loop.
- **Internet Researcher** — a streamed, tool-calling agent (Tavily + scraping).

Interesting signals: per-node latency, time-to-answer dominated by Ollama
generation, prompt-vs-completion token usage, and error/timeout behavior. The
"trace a request through a multi-agent graph" view in Tempo is the money shot for
a portfolio.

---

## 3. What was added (file map)

```
telemetry.py                          # OTEL init + custom metrics (the only app code)
app.py                                # 3 small hooks (init + wrap RAG + wrap Researcher)
pyproject.toml                        # [project.optional-dependencies] observability
docker-compose.observability.yml      # collector + tempo + loki + prometheus + grafana
observability/
  otel-collector-config.yaml          # OTLP in → Tempo + Prometheus + Loki out
  prometheus.yml                      # scrape the collector
  tempo.yaml                          # single-binary local trace store
  loki.yaml                           # single-binary local log store
  grafana/
    provisioning/
      datasources/datasources.yaml    # auto-wire Prometheus + Tempo + Loki
      dashboards/dashboards.yaml      # auto-load the dashboard
    dashboards/langgraph-ollama.json  # the LLM dashboard
```

Logs need no per-call-site changes either: `telemetry.py` attaches an OTel
`LoggingHandler` to the root logger, so every stdlib `logging` call (e.g. the
FAISS cache messages in `tools/rag.py`, the md-mcp connection messages in
`tools/mcp_notes.py`) is exported over OTLP. Records emitted inside an active
span carry its trace_id, so in Grafana you can jump from a log line to its
trace ("View trace") and from a span to its log lines ("Logs for this span").

The agent code (`mm_agent.py`, `rag_research_chatbot.py`, `web_researcher.py` and
their LangGraph nodes) was **not touched**. All per-node/per-LLM tracing comes
from auto-instrumentation.

---

## 4. The app-side code, explained

### 4.1 `telemetry.py` — three responsibilities

**(a) Idempotent init.** Streamlit re-runs the script top-to-bottom on *every*
interaction. If `init_telemetry()` set up exporters each time, you'd get
duplicate pipelines and leaked threads. A module-level `_initialized` flag makes
calls 2..N no-ops:

```python
def init_telemetry() -> bool:
    global _initialized
    if _initialized:
        return True      # already done this process — do nothing
    ...
    _initialized = True
```

> This is *the* Streamlit gotcha. The alternative idiom is to wrap setup in
> `@st.cache_resource`, which guarantees one execution per process. The plain
> module-global guard used here does the same job with no Streamlit dependency.

**(b) Tracing + auto-instrumentation.** We stand up a `TracerProvider` with an
OTLP exporter, then let OpenInference instrument LangChain:

```python
LangChainInstrumentor().instrument(tracer_provider=provider)
```

OpenInference hooks the LangChain **core callback** layer, so it captures every
graph node and `ChatOllama` call — *including the new `langchain-ollama` partner
package* — with zero changes to the agents. Token counts ride along in the spans.

**(c) Custom metrics.** Auto-traces are great for *one* request; for dashboards
you want pre-aggregated metrics. We define four instruments:

| Instrument               | OTEL type     | Prometheus name                    | Use                |
| ------------------------ | ------------- | ---------------------------------- | ------------------ |
| `llm.requests`         | Counter       | `llm_requests_total`             | rate, error ratio  |
| `llm.request.duration` | Histogram     | `llm_request_duration_seconds_*` | p50/p95/p99        |
| `llm.tokens`           | Counter       | `llm_tokens_total`               | tokens/sec by type |
| `llm.active_requests`  | UpDownCounter | `llm_active_requests`            | in-flight gauge    |

Note the **histogram buckets** are overridden via a `View` to seconds-scale
boundaries `(0.25 … 120)` — the SDK defaults top out around 10 and would lump all
your slow LLM calls into one bucket, making `histogram_quantile` useless.

**(d) Graceful degradation.** Every path is wrapped so a missing package or a
down collector prints a line and returns `False` instead of crashing the app.
Set `OTEL_SDK_DISABLED=true` to turn it all off.

### 4.2 `app.py` — three hooks only

```python
import telemetry
telemetry.init_telemetry()          # once, at import (idempotent)
```

RAG path (`run_chatbot_graph`):

```python
with telemetry.track_request(RAG_CHATBOT_AGENT, model):
    output = graph.invoke(input, config=config)
p, c = telemetry.extract_token_usage(output)
telemetry.record_tokens(RAG_CHATBOT_AGENT, model, p, c)
```

Internet Researcher path (streamed):

```python
with telemetry.track_request(INTERNET_RESEARCHER, model_selection):
    for s in langgraph_chain.stream(...):
        ...
```

`track_request` is a context manager: it increments the in-flight gauge, records
latency on exit, and tags the request `status="error"` if the body raises (then
re-raises — telemetry never swallows your errors).

**Token extraction** is best-effort: `langchain-ollama`'s `ChatOllama` exposes
`usage_metadata` (`input_tokens` / `output_tokens`); older variants used
`response_metadata` (`prompt_eval_count` / `eval_count`). `extract_token_usage`
tries both and falls back to `0`. (The streamed Researcher path is timed but not
token-counted manually — its tokens still appear in the Tempo spans.)

---

## 5. The backend configs, explained

- **`otel-collector-config.yaml`** — one `otlp` receiver; a `traces` pipeline
  exporting to `tempo:4317`; a `metrics` pipeline exporting to a Prometheus text
  endpoint on `:8889`. `resource_to_telemetry_conversion: enabled` turns OTEL
  resource attributes (like `service.name`) into Prometheus labels.
- **`prometheus.yml`** — scrapes the collector's `:8889` every 10s. We do **not**
  scrape Streamlit directly (its rerun model makes a self-hosted `/metrics`
  endpoint awkward); the app pushes via OTLP instead.
- **`tempo.yaml`** — single-binary Tempo with local file storage; accepts OTLP on
  `:4317` inside the compose network.
- **Grafana provisioning** — datasources (Prometheus uid `prometheus`, Tempo uid
  `tempo`) and the dashboard are auto-loaded on startup. No manual setup, and the
  dashboard is version-controlled JSON.

---

## 6. Running it

### Prerequisites

- Docker Desktop running.
- Ollama running on the host with the model pulled (`.env` → `OLLAMA_MODEL`,
  currently `glm-5:cloud`).
- uv installed; project synced.

### Steps

```bash
# 1. Install OTEL deps into the uv environment (optional group)
uv sync --extra observability

# 2. Start the observability backends
docker compose -f docker-compose.observability.yml up -d

# 3. Point the app at the collector (PowerShell example)
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"

# 4. Run the app as usual
uv run streamlit run app.py

docker compose -f docker-compose.observability.yml down
```

Now use the **RAG Chatbot Agent** (or **Internet Researcher**) in the UI a few
times, then open:

- **Grafana** → http://localhost:3001 (admin/admin) → dashboard
  *"LangGraph + Ollama — LLM Observability"*. Panels fill in within ~10–20s
  (scrape + export interval).
- **Tempo** (in Grafana → Explore → Tempo datasource) → search by service
  `langgraph-ollama` → open a trace → see the graph nodes and the Ollama LLM span
  with token attributes.
- **Prometheus** → http://localhost:9090 → try `rate(llm_requests_total[5m])`.

### Quick sanity checks

- Collector receiving data? `curl http://localhost:8889/metrics | grep llm_`
- Prometheus target up? http://localhost:9090/targets → `otel-collector` = UP.
- No data in Grafana? Almost always (1) you didn't set
  `OTEL_EXPORTER_OTLP_ENDPOINT`, or (2) you haven't sent a request yet.

---

## 7. The dashboard panels (and the PromQL behind them)

| Panel                | PromQL                                                          | Teaches                   |
| -------------------- | --------------------------------------------------------------- | ------------------------- |
| Request rate         | `sum(rate(llm_requests_total[5m]))`                           | counters +`rate()`      |
| Error ratio          | `…{status="error"} / …`                                     | label filtering, ratios   |
| In-flight            | `sum(llm_active_requests)`                                    | gauges (UpDownCounter)    |
| Latency p50/p95/p99  | `histogram_quantile(0.95, sum(rate(..._bucket[5m])) by (le))` | histogram quantiles       |
| Token throughput     | `sum(rate(llm_tokens_total[5m])) by (type)`                   | `by ()` grouping        |
| Rate by agent/status | `sum(rate(llm_requests_total[5m])) by (agent, status)`        | multi-agent breakdown     |
| Avg latency          | `rate(..._sum) / rate(..._count)`                             | histogram sum/count trick |

The `$agent` dashboard variable is populated from
`label_values(llm_requests_total, agent)` — pick an agent to filter all panels.

> **Naming note:** OTEL → Prometheus renames metrics: dots become underscores,
> counters get `_total`, and the histogram's `s` unit becomes `_seconds`. That's
> why `llm.request.duration` is queried as `llm_request_duration_seconds_bucket`.

---

## 8. How to demo it (the 2-minute story)

1. Open the Grafana dashboard side-by-side with the app.
2. Send a few RAG queries, then an Internet Researcher query; watch **request
   rate** and **token throughput** climb and the `$agent` panel split by agent. *"List the markdown files from your md-mcp knowledge base"*
3. Point at **p95 latency** — "this is Ollama generation time, not network."
4. Jump to **Tempo**, open one trace — "here's that same request broken down by
   graph node; the `rag` node did retrieval, the `conversation` node called the
   LLM." Click the LLM span to show prompt/completion token attributes.
5. Punchline: "the app only emits OTLP — Prometheus, Tempo, and Grafana are all
   swappable behind the Collector."

---

## 9. Extending it (good next exercises)

- **Span-level metrics in Grafana**: enable Tempo's metrics-generator to derive
  RED metrics from spans automatically.
- **Per-node latency metric**: add a custom histogram keyed by `node_name` so you
  get a dashboard panel (not just traces) of where time goes inside the graph.
- **Tool spans for the Researcher**: Tavily search + `scrape_webpages` already
  appear as spans — add a tool-call counter metric for a dedicated panel.
- **Alerts**: a Prometheus alert rule on `p95 > 30s` or `error ratio > 5%`.
- **Logs**: add Loki + the OTEL logs pipeline for the third pillar.

---

## 10. Troubleshooting cheatsheet

| Symptom                        | Likely cause                        | Fix                                                                    |
| ------------------------------ | ----------------------------------- | ---------------------------------------------------------------------- |
| App logs`init failed`        | OTEL deps not installed             | `uv sync --extra observability`                                      |
| Grafana panels empty           | No requests sent, or wrong endpoint | send a request; check`OTEL_EXPORTER_OTLP_ENDPOINT`                   |
| `otel-collector` target DOWN | collector not up / port clash       | `docker compose ... ps`, free `:8889`                              |
| No spans in Tempo              | LangChain instrumentation failed    | check app log`LangChain auto-instrumentation unavailable`            |
| Latency all in one bucket      | histogram buckets default           | already fixed via the`View`; confirm you're on this `telemetry.py` |
| uv resolver conflict           | openinference vs langchain 0.3.x    | relax the`openinference` pin in `pyproject.toml`                   |

---

## 11. One-line summary per component

- **OpenTelemetry** — vendor-neutral SDK/protocol the app uses to emit traces + metrics.
- **OpenInference** — auto-instruments LangChain so graph nodes/LLM calls become spans for free.
- **Collector** — receives OTLP, routes traces→Tempo and metrics→Prometheus.
- **Prometheus** — scrapes + stores time-series metrics; queried with PromQL.
- **Tempo** — stores distributed traces; queried in Grafana.
- **Grafana** — single dashboards/Explore UI over both backends.
