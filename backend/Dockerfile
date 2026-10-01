FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dev dependencies (pytest, ruff) only when requested, so the production image stays small.
ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY . .
RUN chmod +x docker/entrypoint.sh \
    && useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
# PORT is set by some hosts (e.g. Render); WEB_CONCURRENCY tunes gunicorn workers.
# exec so gunicorn receives SIGTERM directly and shuts down gracefully.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3}"]
