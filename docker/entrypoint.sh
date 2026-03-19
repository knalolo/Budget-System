#!/bin/sh
# =============================================================
# Docker entrypoint for the procurement system web container.
# Waits for PostgreSQL, runs migrations, collects static files,
# then starts Gunicorn.
# =============================================================

set -e

# ------------------------------------------------------------------
# Wait for the database to become available
# ------------------------------------------------------------------

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."
until nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; do
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
# Start Gunicorn
# ------------------------------------------------------------------

WORKERS="${GUNICORN_WORKERS:-4}"
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
