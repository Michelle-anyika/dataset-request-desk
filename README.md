# Dataset Request Desk

[![CI](https://github.com/Michelle-anyika/dataset-request-desk/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Michelle-anyika/dataset-request-desk/actions/workflows/ci.yml)

Internal platform for a robotics data collection company. Clients request datasets of robot teleoperation
episodes, operators fulfil them, and clients accept or reject the delivery.

**Stack:** Django REST Framework · PostgreSQL · React (Vite + TypeScript) · Docker · GitHub Actions

## Live

| Environment | Web app | API | Accounts |
|---|---|---|---|
| **Production** | <https://dataset-request-desk-ten.vercel.app> | `desk-api-91nj.onrender.com` | created by an admin; no demo accounts |
| **Dev** | <https://dataset-request-desk-dev.vercel.app> | [Swagger](https://desk-api-dev.onrender.com/api/docs/) | the [demo accounts](#demo-accounts) below |

Hosted on free plans: after 15 minutes without traffic the API sleeps, and the first request can take about a
minute. `develop` deploys to dev and `main` to production, each after CI passes, production also after approval
([docs/deployment.md](docs/deployment.md)).

## Documentation

| | |
|---|---|
| 📄 **Architecture** | [PDF](docs/architecture.pdf) · [Markdown](docs/architecture.md) (the source; diagrams render on GitHub) |
| 🗂 **Data model** | [Diagram (dbdiagram.io)](https://dbdiagram.io/d/dataset-request-desk-erd-6a1d23a6f15b4b045241ea4a) · [docs/erd.dbml](docs/erd.dbml) (the source, with every constraint and note) |
| 🧠 **Design notes** | [NOTES.md](NOTES.md): decisions, trade-offs, security, scale, AI tooling |
| ✅ **Testing** | [docs/testing.md](docs/testing.md) · [docs/performance.md](docs/performance.md) |
| 🔐 **Security** | [docs/security.md](docs/security.md) |
| 🚀 **Deployment** | [docs/deployment.md](docs/deployment.md) |
| 🗺 **Plan and decision log** | [PLAN.md](PLAN.md) |

## Run it

Requirements: Docker with Compose v2.

```bash
docker compose up --build
```

This starts PostgreSQL, applies the migrations, creates the demo accounts, imports the demo episode export and
starts the scheduler. Then open:

- **the web app** on <http://localhost:8080> (nginx serves the React app and forwards `/api` to the API);
- **the API** on <http://localhost:8000>, with Swagger at <http://localhost:8000/api/docs/>.

No `.env` file is needed: every setting has a local default. To override one, copy `.env.example` to `.env`. A real
`.env` is never committed (it's in `.gitignore`); deployed environments keep their settings in Render and GitHub.

### Demo accounts

Created from [`backend/seed/users.json`](backend/seed/users.json) by `python manage.py seed`, which runs on start
when `SEED_DEMO_DATA=true` (the local and dev default). Passwords are stored as Argon2id hashes, never in plain text.

| Role | Email | Password |
|---|---|---|
| Admin | `admin@example.com` | `admin123` |
| Operator | `ops1@example.com`, `ops2@example.com` | `ops123` |
| Client | `client-a@example.com` (Acme Robotics), `client-b@example.com` (Beta Labs) | `client123` |

Seeding is safe to repeat: existing accounts are never modified. These passwords are public, so
`SEED_DEMO_DATA` stays off in production. There is no public sign-up: admins create accounts and choose roles
(**Users** page, or `POST /api/users/`).

## Run the tests

```bash
docker compose run --rm api pytest                  # backend: unit and integration, against PostgreSQL

cd frontend && npm ci && npm test                   # frontend: components and pages (Vitest + Testing Library)
npm run e2e:install && npm run e2e                  # browser journeys with accessibility checks, against
                                                    # the running stack (docker compose up)
```

Backend tests run against PostgreSQL (never SQLite), because the domain rules rely on Postgres features. CI also
runs API fuzzing, CodeQL, SonarCloud and dependency audits on every pull request, and an OWASP ZAP scan and a k6
load test on `develop` and nightly. The full strategy is in [docs/testing.md](docs/testing.md).

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

## Importing episodes

The recording system's export, as **CSV or Excel (`.xlsx`, first sheet)**, is imported with a report of what
was created, updated, unchanged and skipped, and why. Importing the same file again changes nothing. The decisions for each messy case are in
[PLAN.md §8](PLAN.md#8-csv-import-decisions-per-messy-case).

```bash
docker compose exec api python manage.py import_episodes seed/episodes.csv --as ops1@example.com
# 190 rows: 0 created, 0 updated, 173 unchanged, 17 skipped (9 imported after fixes). Report: import #2.
#   line   50  duplicate_in_file          Same episode as line 38.
#   line  162  unknown_robot              Robot 'arm-99' is not a known robot.
#   ...
```

Or `POST /api/imports/` with the file (operators and admins), then `GET /api/imports/{id}/` and
`GET /api/imports/{id}/issues/?severity=skipped`, or the **Imports** page. Uploads are limited to `.csv` and
`.xlsx` and to `IMPORT_MAX_UPLOAD_BYTES` (20 MB by default). A workbook that would unpack to more than 200 MB is
refused. On start, the demo export in `backend/seed/episodes.csv` is imported once.

### Migrating the spreadsheet's requests

Admins can move the requests tracked in the old operations spreadsheet into the platform: **Migrate requests**
page, `POST /api/request-imports/preview/` then `POST /api/request-imports/`, or the command below. A preview
shows what each row would do before anything is saved. Rows are matched on the spreadsheet's `reference`, so
running the same file again creates nothing.

```bash
docker compose exec api python manage.py import_requests requests.csv --as admin@example.com           # preview
docker compose exec api python manage.py import_requests requests.csv --as admin@example.com --commit  # import
```

Columns: `reference, client_email, task_name, episodes_requested, deadline, notes, status`. Unknown clients and
invalid values are reported, never guessed. A row marked `delivered` is refused, because delivery needs its
episodes assigned here first.

## Analytics

`GET /api/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD` (operators and admins; inclusive UTC dates, last 30 days by
default, at most a year) returns:

- `episodes_per_day`: episodes recorded per day per robot;
- `requests.by_status`: requests submitted in the range, by current status;
- `requests.median_hours_to_delivery`: median time from submission to **first** delivery (rework doesn't reset
  the clock), with `delivered_count`, the number of requests it's based on;
- `top_tasks_by_good_episodes`: the top 5 task names by good episodes.

Every number is aggregated by PostgreSQL in four queries (`apps/analytics/queries.py`): `GROUP BY` for the counts
and `percentile_cont(0.5)` for the median. No rows are loaded into Python to be counted.

### Measured at 200,000 episodes

Generated with `backend/seed/generate_episodes.py 200000` (one year of data) on a laptop in Docker:

| | Result |
|---|---|
| Import (200k rows, all new) | 49 s |
| Re-import of the same file | 22 s, 0 created, 200,000 unchanged |
| Analytics, 30-day range (HTTP, all four metrics) | 0.17 s |
| Analytics, one-year range | 0.71 s |
| Episodes per day, 30 days | index scan on `(recorded_at, robot)`, 16,537 rows in 33 ms |
| Top tasks, one year | parallel sequential scan, 48 ms (60% of rows are good, so reading the table beats the index) |

### At 5 million episodes

Expected, not measured: everything above grows with the number of episodes **inside the range**, not with the
table size.

- **30-day ranges stay fast:** about 400k rows per month at that size, read by an index range scan; expect well
  under a few seconds.
- **Year-long ranges break first:** they read most of the table (millions of rows) on every request.
- **The episode list's `COUNT(*)`** for pagination also becomes slow on unfiltered queries.

What we'd change, in order:

1. **Daily rollup table** `episode_daily_counts(day, robot_id, task_name, quality, count)`, updated by the
   import (the only writer of episodes). Analytics then reads days × robots × tasks rows, independent of the
   number of episodes.
2. **Monthly partitions** of `episodes` on `recorded_at`, so date ranges only touch the months they cover.
3. **Keyset pagination** for the episode list instead of `COUNT(*)` and `OFFSET`.
4. **`COPY` into a staging table** plus `INSERT … ON CONFLICT` for imports, typically several times faster than
   ORM bulk inserts.

## Notifications and reminders

So that nothing stalls silently (PLAN.md §7.4):

| When | Who hears | How |
|---|---|---|
| A request is submitted | every active operator | in-app |
| A request is delivered | the client | in-app and email |
| A delivery is accepted / rejected | the operator who delivered it | in-app / in-app and email with the reason |
| A delivery waits 3 days for a decision | the client, every 3 days, at most 3 times | in-app and email |
| Still no decision after that | the operator who delivered it | in-app and email |
| A deadline is 2 days away and nothing is delivered | every active operator, once | in-app |

- Notifications are written in the same transaction as the status change. Emails work as an **outbox**: the
  request only records them, so it never waits for a mail server, and a rolled-back change never emails anyone.
- The `scheduler` container runs `python manage.py send_reminders` every minute. It's idempotent: it sends
  pending emails (retrying failed ones), creates due reminders and warnings, and removes expired token blacklist
  entries. Its checks run in a fixed number of SQL queries, however many requests are open.
- Locally, emails go to the console: `docker compose logs api scheduler`. In the deployed environments a
  scheduled GitHub workflow runs the same command every 15 minutes
  ([docs/deployment.md](docs/deployment.md#scheduled-work)). The inbox API is
  `GET /api/notifications/`, `GET /api/notifications/summary/`, `POST /api/notifications/{id}/read/` and
  `POST /api/notifications/read-all/`.

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

**Error reporting:** set `SENTRY_DSN` to send unhandled errors, and `ERROR` log lines such as a detected
refresh-token theft, to Sentry. Each event carries the request ID and user ID only. Authorization headers,
cookies, request bodies, query strings and emails are removed before anything leaves the server. Off when
`SENTRY_DSN` is empty (the local default).

## Configuration

All configuration is read from environment variables; `.env.example` lists each one. Missing required values
(`DJANGO_SECRET_KEY`, `DATABASE_URL`) stop the app at startup with a clear error. Where each deployed setting
lives is described in [docs/deployment.md](docs/deployment.md#configuration).

## Contributing

Branch naming, commit format and the TDD workflow are described in [CONTRIBUTING.md](CONTRIBUTING.md).
