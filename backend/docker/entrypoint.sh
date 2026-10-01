#!/bin/sh
# Prepares the database, then runs the container command (gunicorn by default, or e.g. pytest).
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

# Demo accounts have publicly known passwords: only for local and dev environments, never production.
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
    python manage.py seed
fi

exec "$@"
