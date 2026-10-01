# Dataset Request Desk

[![CI](https://github.com/Michelle-anyika/dataset-request-desk/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Michelle-anyika/dataset-request-desk/actions/workflows/ci.yml)

Internal platform for a robotics data collection company. Clients request datasets of robot teleoperation
episodes, operators fulfil them, and clients accept or reject the delivery.

**Stack:** Django REST Framework · PostgreSQL · React (Vite + TypeScript) · Docker · GitHub Actions

> 🚧 Work in progress. See [PLAN.md](PLAN.md) for the implementation plan,
> [docs/architecture.md](docs/architecture.md) for the architecture and [docs/erd.dbml](docs/erd.dbml) for the
> data model.

## Run it

Requirements: Docker with Compose v2.

```bash
docker compose up --build
```

This starts PostgreSQL, applies database migrations, creates the demo accounts and runs the API on
<http://localhost:8000>. No `.env` file is needed: every setting has a local default. To override one, copy
`.env.example` to `.env`.

### Demo accounts

Created from [`backend/seed/users.json`](backend/seed/users.json) by `python manage.py seed`, which runs on start
when `SEED_DEMO_DATA=true` (the local default). Passwords are stored as PBKDF2 hashes, never in plain text.

| Role | Email | Password |
|---|---|---|
| Admin | `admin@example.com` | `admin123` |
| Operator | `ops1@example.com`, `ops2@example.com` | `ops123` |
| Client | `client-a@example.com` (Acme Robotics), `client-b@example.com` (Beta Labs) | `client123` |

Seeding is safe to repeat: existing accounts are never modified. These passwords are public, so
`SEED_DEMO_DATA` stays off in production.

## Run the tests

```bash
docker compose run --rm api pytest
```

Tests run against PostgreSQL (never SQLite), because the domain rules rely on Postgres features.

<details>
<summary>Without Docker (backend only, needs a local PostgreSQL)</summary>

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DJANGO_SECRET_KEY=dev DATABASE_URL=postgres://desk:desk@localhost:5432/desk
pytest
```
</details>

## Authentication

Email and password login with short-lived tokens. Full design and threat model: [docs/security.md](docs/security.md).

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login/` | Returns a 10-minute access token and the user; sets a 12-hour refresh token in an `HttpOnly` cookie |
| `POST /api/auth/refresh/` | Rotates the refresh cookie and returns a new access token |
| `POST /api/auth/logout/` | Ends this session |
| `POST /api/auth/logout-all/` | Ends every session of the current user |
| `GET /api/auth/me/` | Current user |

Send the access token as `Authorization: Bearer <token>`. Every other endpoint requires it. Logins are throttled per
IP and per email, passwords are hashed with Argon2id, and reusing an old refresh token ends all of that user's
sessions.

**API docs:** Swagger UI at <http://localhost:8000/api/docs/> when `API_DOCS_ENABLED` is on (the local default).

## Operations

**Health check:** `GET /health` (no authentication) returns `200 {"status": "ok", "db": "ok"}`, or
`503 {"status": "error", "db": "unavailable"}` when the database can't be reached. Docker Compose uses it as the
API container's healthcheck.

**Logging:** every request writes one JSON line to stdout:

```json
{"ts": "2026-10-01T09:15:02.481Z", "level": "INFO", "logger": "desk.request", "message": "GET /health 200",
 "method": "GET", "path": "/health", "status": 200, "duration_ms": 0.82, "user_id": null,
 "request_id": "6ecc8656ead64edf82dcbe9a58f9fc2e"}
```

- `level` follows the status: `INFO` below 400, `WARNING` for 4xx, `ERROR` for 5xx.
- `request_id` is taken from a safe incoming `X-Request-ID` header or generated, and returned in the response
  header, so a user-reported problem can be traced to its log line.
- Query strings are not logged, since they can carry tokens or personal data.
- `LOG_LEVEL` sets the minimum level (default `INFO`).

## Configuration

All configuration is read from environment variables; `.env.example` lists each one. Missing required values
(`DJANGO_SECRET_KEY`, `DATABASE_URL`) stop the app at startup with a clear error.

## Contributing

Branch naming, commit format and the TDD workflow are described in [CONTRIBUTING.md](CONTRIBUTING.md).
