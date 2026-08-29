# syntax=docker/dockerfile:1

# ------------------------------------------------------------------------------
# Stage 1: Build virtual environment with uv
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Install the uv binary directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build/system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    graphviz \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies using lockfile (cached layer for fast rebuilds)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --extra observability

# Copy application source tree
COPY . .

# Complete project sync
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra observability

# ------------------------------------------------------------------------------
# Stage 2: Minimal runtime image
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Install runtime system dependencies (graphviz for LangGraph topologies, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy built application and virtualenv from builder stage
COPY --from=builder /app /app

# Create and switch to non-root user
RUN useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose venv binary path and standard Streamlit settings
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py"]
