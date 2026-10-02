#!/usr/bin/env sh
# Fuzz the running stack with Schemathesis (config: fuzz/schemathesis.toml).
#
#   docker compose up -d --wait          # ideally production-like: DJANGO_DEBUG=false, raised rate limits
#   sh fuzz/run.sh
#
# The schema is exported from the api container (Swagger is off in production-like mode), and the token is
# minted there too, as the seeded admin: no password in this script. Reports go to fuzz/report/.
set -eu

PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
# On Windows (Git Bash), Docker needs the Windows form of the path.
HERE="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
IMAGE="schemathesis/schemathesis:4.29.0@sha256:5586e94460479271714d47613175b3620c44b38b3e1babc936636108f1672a9e"
# On Linux the container must run as the calling user to write the reports into this checkout.
# (Docker Desktop on Windows and macOS maps file ownership itself.)
USER_FLAG=""
[ "$(uname -s)" = "Linux" ] && USER_FLAG="--user $(id -u):$(id -g) --env HOME=/tmp"

mkdir -p fuzz/report
docker compose exec -T api python manage.py spectacular --format openapi-json > fuzz/report/schema.json
FUZZ_TOKEN="$(docker compose exec -T api python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.accounts.sessions import issue_tokens
print(issue_tokens(get_user_model().objects.get(email='admin@example.com'))[0])
" | tail -n 1)"

# Working directory fuzz/report/ (git-ignored): Schemathesis keeps its cache and HTML coverage report there.
# shellcheck disable=SC2086  # USER_FLAG is empty or several words, on purpose
MSYS_NO_PATHCONV=1 docker run --rm $USER_FLAG --network "${PROJECT}_default" \
  -e FUZZ_TOKEN="$FUZZ_TOKEN" \
  -v "$HERE:/fuzz" -w /fuzz/report \
  "$IMAGE" --config-file /fuzz/schemathesis.toml run /fuzz/report/schema.json \
  --url http://api:8000 --seed "${FUZZ_SEED:-1}" \
  --report junit --report-dir /fuzz/report
