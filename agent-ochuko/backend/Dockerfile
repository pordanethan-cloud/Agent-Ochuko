# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# Agent Ochuko — FastAPI Backend Dockerfile
# Multi-stage build: builder installs deps, runtime is lean final image.
# Python 3.11 — matches Azure Functions runtime for consistency.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies (needed for some C-extension packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer cache: only re-runs if requirements change)
COPY requirements.txt .

# Install into a target directory for clean copy to runtime stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Install Node.js, NPM, curl, and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Security: run as non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Create sandbox libraries cache directory with appropriate ownership
RUN mkdir -p /app/sandbox_libs && chown -R appuser:appgroup /app/sandbox_libs

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# Switch to non-root user
USER appuser

# Expose the port uvicorn will listen on
EXPOSE 8000

# Health check for Docker daemon (Container Apps uses its own probe)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Start uvicorn with:
#   --host 0.0.0.0        — listen on all interfaces (required in container)
#   --workers 1           — single worker (Container Apps scales by replicas, not workers)
#   --no-access-log       — structured logging via OpenTelemetry instead
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
