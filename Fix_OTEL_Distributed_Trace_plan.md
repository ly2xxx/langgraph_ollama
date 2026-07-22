# Fix OpenTelemetry Distributed Trace Propagation Between langgraph_ollama and md-mcp

Fix the missing span propagation between `langgraph_ollama` and `md-mcp` so that `md-mcp`'s server-side spans land in the same distributed trace as the agent run in Grafana/Tempo.

## Root Cause Analysis

1. **Unwrapped Coroutine Bypass in `StructuredTool`**:
   In [mcp_notes.py](file:///h:/code/yl/langgraph_ollama/tools/mcp_notes.py), `_sync_wrap` wraps `_run` to attach the OpenInference span context before executing the tool. However, `StructuredTool.from_function` was registered with `coroutine=async_tool.ainvoke` (the raw unwrapped MCP tool). Whenever an async caller or LangGraph invokes `.ainvoke()`, LangChain calls `coroutine` directly, bypassing `_run` and sending outbound HTTP requests without attaching the OTel `traceparent` context.

2. **`callbacks` Parameter & Span Lookup Inflexibility**:
   - `_openinference_span_context` checked `getattr(callbacks, "parent_run_id", None)`. In LangChain tool calls, `callbacks` may be a `CallbackManagerForToolRun` where `run_id` is the tool span ID and `parent_run_id` is the parent agent span ID. Checking `run_id` first with fallback to `parent_run_id` guarantees locating the active OpenInference span.
   - `callbacks` can be passed by LangChain as keyword argument `run_manager` or `callbacks` inside `kwargs`. If positional `callbacks` is `None`, `_run` needs to inspect `kwargs`.
   - Internal kwargs (like `run_manager`) should be stripped before forwarding `kwargs` to `async_tool.ainvoke()`.

3. **Header Case Sensitivity in `md-mcp`**:
   In [telemetry.py](file:///h:/code/yl/md-mcp/md_mcp/telemetry.py), `headers.get("traceparent")` extracts W3C trace context. Normalizing header keys to lowercase guarantees extraction across all ASGI HTTP server header structures.

## Proposed Changes

### langgraph_ollama

#### [MODIFY] [mcp_notes.py](file:///h:/code/yl/langgraph_ollama/tools/mcp_notes.py)
- Update `_openinference_span_context(callbacks)` to handle `callbacks` as `CallbackManagerForToolRun`, `CallbackManager`, or dict, checking both `run_id` and `parent_run_id`.
- Create both synchronous `_run` and asynchronous `_arun` wrappers inside `_sync_wrap`.
- Ensure `_sync_wrap` passes `coroutine=_arun` to `StructuredTool.from_function` so that both `.invoke()` and `.ainvoke()` attach the active OTel span context before calling `async_tool.ainvoke()`.
- Filter out internal LangChain parameters (like `run_manager`) before forwarding `kwargs` to `async_tool.ainvoke()`.

---

### md-mcp

#### [MODIFY] [telemetry.py](file:///h:/code/yl/md-mcp/md_mcp/telemetry.py)
- Robustly normalize incoming HTTP request headers in `_parent_context()` to ensure case-insensitive lookup for `"traceparent"`.

## Verification Plan

### Automated Verification
1. Run Python unit test script verifying:
   - `_openinference_span_context` successfully retrieves the active span context from OpenInference callback manager.
   - Outbound `httpx` HTTP requests carry the `traceparent: 00-{trace_id}-{span_id}-01` header for both `.invoke()` and `.ainvoke()`.
   - `md-mcp`'s `_parent_context()` extracts the traceparent context from the HTTP request headers.

### Manual Verification
1. Run pre-flight check `.\demo.ps1 -ChecksOnly` to verify container setups.
