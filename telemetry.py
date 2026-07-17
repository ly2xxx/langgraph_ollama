"""
OpenTelemetry instrumentation for the LangGraph + Ollama Streamlit app.

Design goals
------------
1. **Zero-friction with Streamlit.** Streamlit re-runs this whole script top to
   bottom on every user interaction. ``init_telemetry()`` is therefore
   *idempotent*: a module-level guard makes the 2nd..Nth call a no-op, so we set
   up exporters and instrumentation exactly once per Python process.
2. **Never break the app.** If the OTEL packages are not installed, or the
   collector is down, the app must still run. Every public function degrades to
   a no-op instead of raising.
3. **Auto + manual.** OpenInference auto-instruments LangChain/LangGraph (one
   span per graph node + per LLM call, with token counts). On top of that we
   record a few *custom* metrics (request count, latency, tokens) that make for
   clean Prometheus/Grafana panels.
4. **Logs ride along.** A ``LoggingHandler`` on the root logger ships every
   stdlib ``logging`` record over OTLP (collector → Loki). Records emitted
   inside an active span automatically carry trace_id/span_id, so log lines
   link to their Tempo trace in Grafana with no per-call-site changes.

Stack note: this app is on the LangChain/LangGraph 0.3.x line using the
``langchain-ollama`` partner package. OpenInference instruments at the LangChain
*core* callback layer, so it captures ``ChatOllama`` regardless of which package
it comes from — no per-agent code changes needed.

Toggle the whole thing off with ``OTEL_SDK_DISABLED=true``.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment / .env)
# ---------------------------------------------------------------------------
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "langgraph-ollama")
# OTLP endpoint of the OpenTelemetry Collector. gRPC default port is 4317.
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
DISABLED = os.getenv("OTEL_SDK_DISABLED", "false").lower() in ("1", "true", "yes")

# Module-level singletons. Populated once by init_telemetry().
_initialized = False
_meter = None
_request_counter = None
_request_duration = None
_token_counter = None
_active_requests = None


def _build_resource():
    from opentelemetry.sdk.resources import Resource

    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.namespace": "demo",
            "deployment.environment": os.getenv("DEPLOY_ENV", "local"),
        }
    )


def _init_tracing(resource) -> None:
    """Traces: one OTLP pipeline + OpenInference LangChain auto-instrumentation."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(provider)

    # Auto-instrument LangChain/LangGraph. Every graph node, chain, and LLM call
    # becomes a span — including prompt/completion token counts — with no changes
    # to the agent code itself.
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)
    except Exception as exc:  # pragma: no cover - optional dependency
        print(f"[telemetry] LangChain auto-instrumentation unavailable: {exc}")

    # Instrument httpx so outbound HTTP requests carry the active span's W3C
    # `traceparent` header. This is what links the agent's trace to remote
    # services that also export OTel — in particular md-mcp tool calls over
    # streamable-http (see tools/mcp_notes.py) show up as child spans of the
    # agent run instead of starting a disconnected trace.
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except Exception as exc:  # pragma: no cover - optional dependency
        print(f"[telemetry] httpx instrumentation unavailable: {exc}")


def _init_logging(resource) -> None:
    """Logs: OTLP pipeline + a handler bridging stdlib ``logging`` into it.

    Existing ``logging.info(...)`` calls across the app (tools/rag.py,
    tools/mcp_notes.py, ...) are exported unchanged. The OTel handler stamps
    each record with the active span's trace_id/span_id, which is what powers
    the Loki ↔ Tempo cross-links provisioned in Grafana.
    """
    import logging

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
    )
    set_logger_provider(provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    root = logging.getLogger()
    root.addHandler(handler)
    # The handler only sees records the root logger lets through. Its default
    # level is WARNING, and tools/rag.py's basicConfig(INFO) is a silent no-op
    # whenever some other handler got attached first — so enforce INFO here
    # rather than depending on import order.
    if root.getEffectiveLevel() > logging.INFO:
        root.setLevel(logging.INFO)

    # One guaranteed line per process start — a smoke signal that the
    # app → collector → Loki pipeline is alive, visible in Grafana.
    logging.getLogger(__name__).info(
        "telemetry logs pipeline active (service=%s, endpoint=%s)",
        SERVICE_NAME,
        OTLP_ENDPOINT,
    )


def _init_metrics(resource) -> None:
    """Metrics: OTLP pipeline + a small set of custom instruments."""
    global _meter, _request_counter, _request_duration, _token_counter, _active_requests

    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import (
        View,
        ExplicitBucketHistogramAggregation,
    )
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )

    # LLM latency spans many seconds, so override the default histogram buckets
    # with boundaries that actually resolve token-generation timings.
    latency_view = View(
        instrument_name="llm.request.duration",
        aggregation=ExplicitBucketHistogramAggregation(
            (0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120)
        ),
    )

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True),
        export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "10000")),
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader], views=[latency_view])
    metrics.set_meter_provider(provider)

    _meter = metrics.get_meter(SERVICE_NAME)
    _request_counter = _meter.create_counter(
        "llm.requests",
        unit="1",
        description="Total LangGraph agent invocations.",
    )
    _request_duration = _meter.create_histogram(
        "llm.request.duration",
        unit="s",
        description="End-to-end agent invocation latency.",
    )
    _token_counter = _meter.create_counter(
        "llm.tokens",
        unit="1",
        description="Tokens consumed/produced, split by type.",
    )
    _active_requests = _meter.create_up_down_counter(
        "llm.active_requests",
        unit="1",
        description="In-flight agent invocations.",
    )


def init_telemetry() -> bool:
    """Initialise OTEL once per process. Safe to call on every Streamlit rerun.

    Returns True if telemetry is active, False if disabled or unavailable.
    """
    global _initialized
    if _initialized:
        return True
    if DISABLED:
        print("[telemetry] OTEL_SDK_DISABLED is set — telemetry off.")
        return False

    try:
        resource = _build_resource()
        _init_tracing(resource)
        _init_metrics(resource)
        # Logs are additive — if the pipeline can't come up, keep traces and
        # metrics rather than failing telemetry as a whole.
        try:
            _init_logging(resource)
        except Exception as exc:  # pragma: no cover - optional pipeline
            print(f"[telemetry] log export unavailable: {exc}")
        _initialized = True
        # ASCII only: a non-ASCII char here raises UnicodeEncodeError on
        # cp1252 Windows consoles, and the enclosing except would then report
        # telemetry as failed even though it initialised fine.
        print(f"[telemetry] OTEL active -> {OTLP_ENDPOINT} (service={SERVICE_NAME})")
        return True
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[telemetry] init failed, running without telemetry: {exc}")
        return False


# ---------------------------------------------------------------------------
# Helpers used by the app
# ---------------------------------------------------------------------------
def extract_token_usage(graph_output) -> tuple[int, int]:
    """Best-effort extraction of (prompt_tokens, completion_tokens).

    langchain-ollama's ChatOllama exposes ``usage_metadata``
    (input_tokens / output_tokens) on the AIMessage. Older/community variants
    instead put Ollama's raw counters in ``response_metadata`` as
    ``prompt_eval_count`` / ``eval_count``. We try both and fall back to 0.
    """
    try:
        if not isinstance(graph_output, dict):
            return 0, 0
        messages = graph_output.get("messages") or []
        if not messages:
            return 0, 0
        last = messages[-1]

        usage = getattr(last, "usage_metadata", None)
        if usage:
            return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))

        meta = getattr(last, "response_metadata", None) or {}
        return int(meta.get("prompt_eval_count", 0)), int(meta.get("eval_count", 0))
    except Exception:
        return 0, 0


def record_tokens(agent: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    if _token_counter is None:
        return
    if prompt_tokens:
        _token_counter.add(prompt_tokens, {"agent": agent, "model": model, "type": "prompt"})
    if completion_tokens:
        _token_counter.add(completion_tokens, {"agent": agent, "model": model, "type": "completion"})


@contextmanager
def track_request(agent: str, model: str):
    """Time an agent invocation and emit request/latency/active metrics.

    Usage:
        with track_request("RAG Chatbot Agent", "glm-5:cloud"):
            output = graph.invoke(...)
    """
    attrs = {"agent": agent, "model": model}
    start = time.perf_counter()
    if _active_requests is not None:
        _active_requests.add(1, attrs)
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        if _request_counter is not None:
            _request_counter.add(1, {**attrs, "status": status})
        if _request_duration is not None:
            _request_duration.record(duration, attrs)
        if _active_requests is not None:
            _active_requests.add(-1, attrs)
