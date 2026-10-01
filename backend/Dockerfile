FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dev dependencies (pytest, ruff) only when requested, so the production image stays small.
# Every package is hash-locked (requirements*.txt are generated from the .in files) and installed from wheels
# only, so no package code runs during installation.
ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes --only-binary=:all: -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --require-hashes --only-binary=:all: -r requirements-dev.txt; \
    fi

# Only what the app needs, never the whole build context.
COPY manage.py pyproject.toml gunicorn.conf.py ./
COPY config ./config
COPY apps ./apps
COPY seed ./seed
COPY docker ./docker
COPY tests ./tests

RUN chmod +x docker/entrypoint.sh \
    && useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
# Settings (threads, timeouts, worker recycling, PORT) are in gunicorn.conf.py.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
