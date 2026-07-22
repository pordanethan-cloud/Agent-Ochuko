# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# Agent Ochuko — Single-Container Dual-Process Dockerfile
# Multi-stage build:
#   Stage 1: Go Builder (compiles Go Edge Gateway binary)
#   Stage 2: Python Builder (installs Python dependencies)
#   Stage 3: Runtime (runs Go Gateway supervisor which spawns Python AI Worker)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Go Edge Gateway Builder ──────────────────────────────────────────
FROM golang:1.22-alpine AS go-builder

WORKDIR /build/gateway

COPY gateway/go.mod ./
# Download Go dependencies (layer cached)
RUN go mod download || true

COPY gateway/ ./

# Tidy dependencies and build optimized static CGO_ENABLED=0 Go Gateway binary
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /build/gateway_app ./cmd/server/main.go

# ── Stage 2: Python Builder ───────────────────────────────────────────────────
FROM python:3.11-slim AS python-builder

WORKDIR /build

# Install build dependencies (needed for C-extension packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY agent-ochuko/backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 3: Runtime Single-Container ─────────────────────────────────────────
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

# Copy installed Python packages from python-builder
COPY --from=python-builder /install /usr/local

# Copy Go Edge Gateway binary from go-builder
COPY --from=go-builder /build/gateway_app /usr/local/bin/gateway
RUN chmod +x /usr/local/bin/gateway

# Copy Python backend application code
COPY agent-ochuko/backend/app/ ./app/

# Ownership setup
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose the public port for Go Edge Gateway
EXPOSE 8000

# Health check for Docker daemon
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Start Go Gateway supervisor (spawns Python worker internally on 127.0.0.1:8001)
ENTRYPOINT ["/usr/local/bin/gateway"]
