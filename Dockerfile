# ============================================================
# Procurement System — Production Dockerfile
# Multi-stage build: builder installs deps, runtime is lean.
# Base image: Python 3.11 slim (Debian Bookworm)
# ============================================================

# ------------------------------------------------------------
# Stage 1: builder — install Python dependencies
# ------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build-time system dependencies required by psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the package manifest first to leverage layer caching
COPY pyproject.toml .

# Install the project and all its runtime dependencies
RUN pip install --upgrade pip && pip install .

# ------------------------------------------------------------
# Stage 2: runtime — lean production image
# ------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime-only system library required by psycopg2 (no gcc needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code
COPY . .

# Create a non-root user for security
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --no-create-home appuser && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/docker/entrypoint.sh

# Create directories for static and media files with correct ownership
RUN mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appgroup /app/staticfiles /app/media

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
