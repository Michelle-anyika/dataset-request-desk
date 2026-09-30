#!/bin/sh
# Prepares the database, then runs the container command (gunicorn by default, or e.g. pytest).
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
