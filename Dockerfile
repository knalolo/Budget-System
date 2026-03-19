# ============================================================
# Procurement System — Production Dockerfile
# Base image: Python 3.11 slim (Debian Bookworm)
# ============================================================

FROM python:3.11-slim AS base

# Prevent .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies required by psycopg2 and general tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Install Python dependencies
# ============================================================

COPY pyproject.toml .

# Install the project and its dependencies without the optional dev extras
RUN pip install --upgrade pip && pip install .

# ============================================================
# Copy application source
# ============================================================

COPY . .

# Collect static files at build time so the image is self-contained.
# SECRET_KEY is a dummy value used only for this build step.
RUN SECRET_KEY=collectstatic-dummy-key \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    DB_NAME=dummy DB_USER=dummy DB_PASSWORD=dummy \
    python manage.py collectstatic --noinput

# ============================================================
# Runtime configuration
# ============================================================

# Ensure the entrypoint script is executable
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
