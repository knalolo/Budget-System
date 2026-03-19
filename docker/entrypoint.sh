#!/bin/sh
# =============================================================
# Docker entrypoint for the procurement system web container.
# Waits for PostgreSQL, runs migrations, collects static files,
# optionally creates a superuser, seeds reference data,
# then starts Gunicorn.
# =============================================================

set -e

# ------------------------------------------------------------------
# Wait for the database to become available
# ------------------------------------------------------------------

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-procurement_user}"
DB_NAME="${DB_NAME:-procurement_db}"

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -q; do
    printf '.'
    sleep 1
done
echo ""
echo "PostgreSQL is ready."

# ------------------------------------------------------------------
# Apply database migrations
# ------------------------------------------------------------------

echo "Running database migrations ..."
python manage.py migrate --noinput

# ------------------------------------------------------------------
# Collect static files
# ------------------------------------------------------------------

echo "Collecting static files ..."
python manage.py collectstatic --noinput --clear

# ------------------------------------------------------------------
# Create superuser (optional — only when env vars are provided)
# ------------------------------------------------------------------

if [ -n "${DJANGO_SUPERUSER_USERNAME}" ] && \
   [ -n "${DJANGO_SUPERUSER_EMAIL}" ] && \
   [ -n "${DJANGO_SUPERUSER_PASSWORD}" ]; then
    echo "Creating superuser '${DJANGO_SUPERUSER_USERNAME}' if not already present ..."
    python manage.py createsuperuser \
        --noinput \
        --username "${DJANGO_SUPERUSER_USERNAME}" \
        --email "${DJANGO_SUPERUSER_EMAIL}" \
        2>/dev/null || echo "Superuser already exists — skipping."
fi

# ------------------------------------------------------------------
# Seed reference data (idempotent)
# ------------------------------------------------------------------

echo "Seeding reference data ..."
python manage.py seed_data

# ------------------------------------------------------------------
# Start Gunicorn
# ------------------------------------------------------------------

WORKERS="${GUNICORN_WORKERS:-3}"
BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "Starting Gunicorn (workers=${WORKERS}, bind=${BIND}) ..."
exec gunicorn config.wsgi:application \
    --workers "$WORKERS" \
    --bind "$BIND" \
    --timeout "$TIMEOUT" \
    --access-logfile - \
    --error-logfile - \
    --log-level info
