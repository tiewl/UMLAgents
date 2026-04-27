# UMLAgents Docker Image
# Multi-stage build for production and development

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY pyproject.toml setup.py ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY umlagents/ ./umlagents/
COPY examples/ ./examples/
COPY schema/ ./schema/
COPY web/ ./web/

# Create non-root user
RUN useradd -m -u 1000 umlagents && chown -R umlagents:umlagents /app
USER umlagents

# Default command (CLI help)
CMD ["umlagents", "--help"]

# ============================================================================
# Development stage with hot reload
# ============================================================================
FROM base AS dev

# Install development dependencies
USER root
RUN pip install --no-cache-dir \
    "fastapi>=0.100" \
    "uvicorn[standard]>=0.23" \
    "websockets>=12.0"
USER umlagents

# Expose WebSocket UI port
EXPOSE 8080

# Default command for development (WebSocket UI)
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]

# ============================================================================
# Production stage (minimal CLI)
# ============================================================================
FROM python:3.11-slim AS production

WORKDIR /app

# Copy source first so pip installs from local tree
COPY pyproject.toml setup.py ./
COPY umlagents/ ./umlagents/
COPY schema/ ./schema/

RUN pip install --no-cache-dir .

# Create non-root user
RUN useradd -m -u 1000 umlagents && chown -R umlagents:umlagents /app
USER umlagents

CMD ["umlagents", "--help"]

# ============================================================================
# Web UI stage (standalone WebSocket UI)
# ============================================================================
FROM python:3.11-slim AS web-ui

WORKDIR /app

# Copy source first so pip installs from local tree
COPY pyproject.toml setup.py ./
COPY umlagents/ ./umlagents/
COPY web/ ./web/

RUN pip install --no-cache-dir ".[web]"

# Create non-root user
RUN useradd -m -u 1000 umlagents && chown -R umlagents:umlagents /app
USER umlagents

EXPOSE 8080

# web/app.py lives at /app/web/app.py — import as web.app from /app
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]