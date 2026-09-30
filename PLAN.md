# Dataset Request Desk: Implementation Plan

> Living document. Tick boxes as we go. Decisions made here get copied into `NOTES.md` at the end.
> **Deadline:** Sunday 04 Oct 2026, 23:59 Kigali (UTC+2). **Target submit:** Sunday 16:00.

---

## 1. Goal

Replace the operations spreadsheet with an internal web platform where:

- **clients** submit dataset requests and accept/reject deliveries,
- **operators** import episodes, work requests through their workflow and assign episodes,
- **admins** manage users and roles.

**Quality bar:** a complete, working, *tested* app with professional engineering around it (CI/CD, code quality gates,
two environments, live URL). We grow scope only after the graded core is solid. The brief says: *"a clean, tested,
honest 70% beats a sprawling 100%"*.

**Stretch item picked:** **Deployment** (public HTTPS, dev and prod environments).

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.13, Django 5.2 LTS, Django REST Framework** | Migrations, auth and password hashing built in; familiar |
| Auth | **djangorestframework-simplejwt** (access 15 min, refresh 1 day) | Stateless; works across the Vercel ↔ Render domains |
| API docs | **drf-spectacular** (OpenAPI, Swagger UI at `/api/docs/`) | Reviewers can explore the API |
| Filtering | **django-filter** | Episode list filters (task, quality, robot, availability) |
| Database | **PostgreSQL 16** | `percentile_cont` for median, partial unique indexes, `jsonb` |
| DB driver | **psycopg 3** | Current driver |
| Logging | Python `logging` + **python-json-logger**, custom request middleware | One JSON line per request |
| Server | **gunicorn** | Production WSGI |
| Frontend | **React 18 + Vite + TypeScript** | Familiar, fast builds |
| UI kit | **MUI (Material UI)** | Clean UI without spending time on design |
| Data fetching | **TanStack Query** + axios | Caching, loading and error states; token interceptor |
| Routing | **React Router** | Role-based protected routes |
| Backend tests | **pytest, pytest-django, factory-boy, pytest-cov** | Readable tests; factories |
| Frontend tests | **Vitest + React Testing Library** (a few key tests only) | |
| Lint/format | **Ruff** (Python), **ESLint + Prettier** (TS), **pre-commit** | |
| Containers | **Docker + docker compose** | One-command startup |
| CI | **GitHub Actions** | Free, lives in the repo, visible to reviewers |
| Code quality | **SonarCloud** (hosted SonarQube, free for public repos) | Quality gate and coverage on every PR |
| Deps | **Dependabot** | Automated dependency PRs |
| Tasks | **GitHub Issues + GitHub Projects** (board) | Linked to PRs/commits and visible to reviewers |
| Hosting | **Render** (API, Docker), **Neon** (Postgres, dev/prod branches), **Vercel** (frontend) | Free tiers, HTTPS by default. *Verify limits on deploy day.* |

---

## 3. Architecture

Full diagrams in **[docs/architecture.md](docs/architecture.md)**: system context, containers, backend components,
request lifecycle, status workflow, CSV import pipeline, deployment and delivery pipeline.

**Where state lives:** all business state is in PostgreSQL. The API is stateless (JWT), so any number of API
containers can run. The frontend holds only UI state; the access token is kept in memory and the refresh token in
`localStorage` (trade-off discussed in NOTES).

### Repository layout

```
dataset-request-desk/
├── backend/
│   ├── config/              # settings (base/dev/prod via env vars), urls, wsgi
│   ├── apps/
│   │   ├── accounts/        # custom User (email login, role), auth + admin user endpoints, seed command
│   │   ├── catalog/         # Robot, Episode, CSV import (service + mgmt command + endpoint)
│   │   ├── requests_desk/   # DatasetRequest, status workflow, events, assignments
│   │   ├── analytics/       # SQL-backed analytics endpoint
│   │   └── core/            # health, logging middleware, permissions, error handler
│   ├── seed/                # users.json, episodes.csv (from candidate pack)
│   ├── tests/
│   ├── Dockerfile
│   └── requirements*.txt
├── frontend/
│   ├── src/ (api/, auth/, pages/, components/)
│   ├── Dockerfile           # build → nginx
│   └── package.json
├── docs/erd.dbml            # paste into dbdiagram.io
├── .github/workflows/       # ci.yml, cd.yml
├── docker-compose.yml
├── PLAN.md  README.md  NOTES.md
```

---

## 4. Git workflow

- **Git flow.** `main` = **production** (PRs from `develop` or `hotfix/*` only). `develop` = **dev/staging**
  (PRs from work branches).
- Branch names: `feat/`, `fix/`, `hotfix/`, `chore/`, `docs/`, `test/`, `refactor/`, `perf/`, `ci/`, `build/` +
  kebab-case slug, e.g. `feat/12-status-transitions`. Hotfixes branch from `main` and are back-merged to `develop`.
- **Conventional Commits:** `feat(requests): enforce status transitions`, `test(import): idempotency on re-run`,
  `fix: ...`, `chore(ci): ...`, `docs: ...`.
- **Enforced, not just agreed:**
  - commitlint (`commitlint.config.mjs`) as a local `commit-msg` hook and in CI on every PR commit and the PR title;
  - branch names by a local pre-commit hook (also blocks commits on `main`/`develop`) and by the CI
    **Branch naming** check, which also validates source → target (e.g. `feat/*` can't PR into `main`).
- **TDD** for domain logic: `test(...)` (red) → `feat(...)` (green) → `refactor(...)` commits.
- PRs are merged with **merge commits** (not squash) so the TDD history stays visible.
- Small commits, one idea each. Every PR links its issue (`Closes #12`) and must pass CI before merge.
- Release: PR `develop → main` titled `release: vX.Y.Z`, tag after merge.
- Full rules: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 5. CI/CD pipeline

```
feature/* ──PR──► develop ──PR──► main
   │                 │              │
   CI                CI + CD(dev)   CI + CD(prod)
```

**CI (`.github/workflows/ci.yml`)** runs on every PR and on push to `develop` and `main`:
1. **backend:** ruff lint + format check → `makemigrations --check` (no forgotten migrations) → pytest against a real
   Postgres service container → coverage.xml
2. **frontend:** `npm ci` → eslint → vitest → `vite build`
3. **sonarcloud:** analysis + quality gate (after the token is added)
4. **docker:** `docker compose build` smoke test (after compose exists)
5. **ci-ok:** single aggregate job, used as the required status check in branch protection

**CD (`.github/workflows/cd.yml`)** runs after CI succeeds on `develop` or `main`:
- trigger the Render deploy hook for the matching environment (dev or prod);
- Vercel builds the frontend from its Git integration (`main` → production, `develop` → dev domain);
- migrations run at container start (`migrate --noinput`), then gunicorn.

| Env | Branch | API | DB | Frontend |
|---|---|---|---|---|
| local | any | docker compose | postgres container | vite dev server / nginx container |
| dev | `develop` | Render service `desk-api-dev` | Neon branch `dev` | Vercel develop domain |
| prod | `main` | Render service `desk-api` | Neon branch `main` | Vercel production |

**Secrets:** never committed. GitHub Actions secrets (`SONAR_TOKEN`, `RENDER_DEPLOY_HOOK_DEV`,
`RENDER_DEPLOY_HOOK_PROD`) plus Render/Vercel environment variables (`DJANGO_SECRET_KEY`, `DATABASE_URL`,
`ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`). `.env.example` documents every variable.

---

## 6. Data model

See `docs/erd.dbml` (render at dbdiagram.io). Summary:

- **users**: email login, `role` ∈ {client, operator, admin}, `is_active` (deactivate, never delete).
- **robots**: known robots (natural key `arm-01`, …). Unknown robots are rejected on import.
- **episodes**: `episode_id` is the natural unique key (upsert target). Indexed on `(recorded_at, robot_id)` and
  `(quality, task_name)` for analytics and filters.
- **import_batches / import_row_issues**: one row per import run and one row per skipped/fixed CSV line. This *is*
  the import report and it is kept.
- **dataset_requests**: owned by a client; `status` column holds the current state.
- **request_status_events**: append-only audit log (from, to, who, when, comment). Source of truth for history and
  for the median submitted→delivered.
- **assignments**: episode ↔ request, with `released_at` for history. **Partial unique index**
  `UNIQUE(episode_id) WHERE released_at IS NULL` guarantees one active request per episode *in the database*, even
  under concurrent requests.

---

## 7. Domain rules (these are the tests)

### 7.1 Authorization (server-side, per endpoint)

| Action | client | operator | admin |
|---|---|---|---|
| Login / refresh / me | ✅ | ✅ | ✅ |
| Create request | ✅ (owner = self) | ❌ | ❌ |
| List/view requests | own only (others → **404**, don't leak existence) | all | all |
| Transition status | accept/reject own delivered only | operator steps | operator steps |
| View request's assignments | own (read-only) | ✅ | ✅ |
| Assign/unassign episodes | ❌ | ✅ | ✅ |
| List episodes | ❌ | ✅ | ✅ |
| Import CSV / view reports | ❌ | ✅ | ✅ |
| Analytics | ❌ | ✅ | ✅ |
| Manage users/roles | ❌ | ❌ | ✅ |
| Inactive user | cannot log in; existing tokens rejected | | |

Decisions to record: admins **cannot** accept/reject on a client's behalf (that step belongs to the client). An admin
cannot deactivate or demote themselves (to avoid locking everyone out).

### 7.2 Status transitions (single state machine, one place in code)

| From → To | Who | Extra rule |
|---|---|---|
| `submitted → in_progress` | operator/admin | |
| `in_progress → delivered` | operator/admin | active assignments ≥ `episodes_requested` |
| `delivered → accepted` | owning client | terminal |
| `delivered → rejected` | owning client | comment (reason) required |
| `rejected → in_progress` | operator/admin | rework |
| anything else | nobody | **409 Conflict** with a clear message |

Every transition runs in a DB transaction with `SELECT … FOR UPDATE` on the request row and writes a
`request_status_events` row. Creating a request writes the initial `NULL → submitted` event.

### 7.3 Assignment rules

- Only `good`/`usable` episodes (`bad` → 400).
- An episode can be active on at most one request (enforced by the DB index; conflict → 409).
- Assign/unassign only while request is `in_progress`. Locked when `delivered`/`accepted`.
- Bulk assign (`episode_ids: [...]`) is all-or-nothing in one transaction.
- Delivered requires count ≥ requested (checked inside the transition transaction).
- Over-assigning (more than requested) is allowed. Decision to record.

---

## 8. CSV import: decisions per messy case

Found by inspecting `seed/episodes.csv` (189 data rows + 2 blank lines). Two kinds of outcome: **fixed** (normalised and imported,
noted in the report) and **skipped** (not imported, reason recorded).

| Case in file | Example | Decision |
|---|---|---|
| Blank lines | lines 191–192 | ignore (counted as `blank_line`) |
| Missing column(s) | `EP-90001,...,30` (5 fields) | **skip** `malformed_row` |
| Quoted comma | `"pick cup, then place"` | valid CSV → import as task name |
| Missing `episode_id` | `,humanoid-01,...` | **skip** `missing_episode_id` |
| Lower-case id | `ep-00003` | normalise to upper → then duplicate rules apply |
| Exact duplicate in file | `EP-00030`, `EP-00074` | keep first, **skip** `duplicate_in_file` |
| Conflicting duplicate in file | `EP-00011` bad vs good; `ep-00003` vs `EP-00003` | keep first, **skip** `conflicting_duplicate` (flag for human review) |
| Robot with whitespace | `" arm-01"` | trim → **fixed** |
| Unknown robot | `arm-99` | **skip** `unknown_robot` |
| Missing robot | `,` | **skip** `missing_robot_id` |
| Task casing/whitespace | `"  Pick Cup "`, `PICK CUP` | trim, collapse spaces, lower-case → **fixed** |
| Date `YYYY-MM-DD HH:MM:SS` | | parse → **fixed** |
| Date with `Z` | `...09:20:00Z` | parse as UTC |
| Date `DD/MM/YYYY HH:MM` | `14/08/2026 09:15` | parse day-first (Rwanda/EU convention) → **fixed** |
| Unparseable date | `not a date` | **skip** `invalid_recorded_at` |
| Future date | `2031-01-01` | **skip** `recorded_at_in_future` |
| Naive timestamps | most rows | treated as **UTC** (assumption, documented) |
| Decimal duration | `45.5` | round to nearest second → **fixed** |
| Missing / `N/A` duration | | **skip** `invalid_duration` |
| Negative / zero duration | `-5` | **skip** `invalid_duration` |
| Implausible duration | `999999` (11.5 days) | **skip** `duration_out_of_range` (max 3600 s, configurable) |
| Quality casing | `Good`, `USABLE` | lower-case → **fixed** |
| Invalid quality | `excellent` | **skip** `invalid_quality` |
| Missing quality | | **skip** `missing_quality` |
| Missing operator name | `EP-90005` | import with `NULL` → **fixed** (non-critical field) |
| Wrong/missing header | | **fail the whole import** with a clear error |

**Idempotency:** upsert keyed on `episode_id` inside one transaction. Per row, the outcome is **created**, **updated**
(the recording system is the source of truth), **unchanged**, or **skipped**. Re-running the same file gives
`0 created, N unchanged`. Special case: an update that would make a currently **assigned** episode `bad` is skipped
(`assigned_episode_conflict`) so the import can't break the assignment rule.
Both entry points share one service: `python manage.py import_episodes <file>` and `POST /api/imports/`.

---

## 9. API (v1)

| Method | Path | Who |
|---|---|---|
| GET | `/health` | public (checks DB) |
| POST | `/api/auth/login/`, `/api/auth/refresh/` | public |
| GET | `/api/auth/me/` | any |
| GET/POST | `/api/users/` | admin |
| PATCH | `/api/users/{id}/` (role, is_active, name) | admin |
| GET/POST | `/api/requests/` | scoped / client |
| GET | `/api/requests/{id}/` | scoped |
| POST | `/api/requests/{id}/transitions/` `{to_status, comment}` | per §7.2 |
| GET | `/api/requests/{id}/events/` | scoped |
| GET/POST | `/api/requests/{id}/assignments/` `{episode_ids}` | scoped read / operator write |
| DELETE | `/api/requests/{id}/assignments/{episode_id}/` | operator |
| GET | `/api/episodes/?task_name=&quality=&robot_id=&available=true&page=` | operator |
| GET/POST | `/api/imports/` (multipart CSV) | operator |
| GET | `/api/imports/{id}/` (report + issues) | operator |
| GET | `/api/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD` | operator |
| GET | `/api/docs/` | Swagger UI |

Errors use one JSON shape: `{"error": {"code": "invalid_transition", "message": "...", "details": {...}}}`.
All lists are paginated.

### Analytics (all computed in SQL)
- **Episodes per day per robot:** `GROUP BY date_trunc('day', recorded_at), robot_id`, filtered on `recorded_at`
  range (uses `ix_episodes_recorded_robot`).
- **Requests by status:** `GROUP BY status` for requests created in range.
- **Median submitted→delivered:** `percentile_cont(0.5) WITHIN GROUP (ORDER BY delivered_at - submitted_at)`, using
  the *first* delivered event per request (decision: rework doesn't reset the clock).
- **Top 5 tasks by good episodes:** `WHERE quality='good' GROUP BY task_name ORDER BY count DESC LIMIT 5`.
- Verified with `EXPLAIN ANALYZE` on 200k+ generated rows; 5M-row discussion in README (range scans on the composite
  index; next steps are a daily rollup table/materialized view and monthly partitioning on `recorded_at`).

### Logging
Middleware emits one JSON line per request:
`{"ts", "level", "method", "path", "status", "duration_ms", "user_id", "request_id"}`. A `request_id` is generated
(or taken from `X-Request-ID`) and returned in a response header. Import runs log a summary line.

---

## 10. Frontend (React)

| Page | Role | Content |
|---|---|---|
| Login | all | email/password, error states |
| My requests | client | table (task, count, deadline, status chip); "New request" dialog |
| Request detail | client | status timeline (events), delivered episodes, **Accept** / **Reject (reason)** |
| Requests queue | operator/admin | all requests, filter by status/client; sort by deadline |
| Request detail | operator/admin | timeline, allowed transition buttons (from API), progress `assigned/requested` |
| Assign episodes | operator/admin | available episodes table, filters `task_name`, `quality` (+ robot), multi-select → assign; remove |
| Imports | operator/admin | upload CSV → report (created/updated/unchanged/skipped + issues table); history |
| Analytics | operator/admin | date range → per-day chart, status counts, median, top 5 tasks |
| Users | admin | list, create, change role, activate/deactivate |

The UI shows only the actions allowed for the user's role, but **the server stays the enforcer**. A tampered UI gets
403/404/409 from the API.

---

## 11. Testing strategy (what we test and why)

Priority is what the reviewers named: **authorization, transitions, assignments, import idempotency**.

**Approach: TDD** for everything below except the frontend. Each rule in §7/§8 starts as a failing test, so the
tables in those sections are the test list. Use pytest-django's `django_db` against real Postgres (not SQLite),
because the partial unique index and `percentile_cont` are Postgres features.

- **Authorization:** matrix test (parametrised role × endpoint → expected status), client A can't see or act on client
  B's request (404), inactive user rejected, operator can't manage users, client can't assign.
- **Transitions:** every valid transition is allowed for the right role; every invalid pair → 409; wrong role → 403;
  delivered blocked below count; reject requires a comment; each change writes an event with actor and timestamp.
- **Assignments:** bad episode rejected; same episode on two requests rejected (including a DB-level test of the
  partial unique index); unassign then reassign works; locked after delivered; bulk is all-or-nothing.
- **Import:** each messy-case row gets the right outcome and reason; **running the same file twice gives no duplicates
  and `0 created`**; changed row gets updated; the assigned→bad conflict.
- **Analytics:** small fixed dataset → exact expected numbers (including the median).
- **Ops:** `/health` 200, and 503 when the DB is down (mocked); a log line has the expected fields.
- **Frontend:** a few tests (login flow, role-based route guard, transition buttons).

One command: `docker compose run --rm api pytest` (and `make test`).

---

## 12. Schedule

### Tue 29 Sep: Foundations
- [x] Repo created, plan, ERD script
- [ ] CI workflow, `develop` branch, branch protection
- [ ] ERD reviewed at dbdiagram.io → adjust
- [ ] User stories → GitHub Issues + Project board
- [ ] Backend scaffold: Django project, settings from env, Dockerfile, docker compose (db + api), `/health`, JSON
      request logging

### Wed 30 Sep: Auth + requests core
- [ ] Custom User model + migrations, seed command (users.json, robots), JWT login/refresh/me
- [ ] Permission classes; admin user management endpoints
- [ ] DatasetRequest + events; state machine service; transition endpoint
- [ ] Tests: authorization matrix, transitions

### Thu 01 Oct: Episodes, import, assignments, analytics
- [ ] Robot/Episode models, CSV import service + command + endpoint + report models
- [ ] Assignment model with partial unique index; assign/unassign endpoints; episode list with filters
- [ ] Analytics endpoint (SQL), EXPLAIN on 200k rows
- [ ] Tests: import (each case + idempotency), assignments, analytics
- [ ] SonarCloud connected

### Fri 02 Oct: Frontend
- [ ] Vite + React + TS + MUI scaffold, auth context, axios interceptor, protected routes
- [ ] Client pages; operator pages (queue, detail, assign); imports; analytics; users
- [ ] Frontend container (nginx) in compose → **full `docker compose up` from clean clone**

### Sat 03 Oct: Deploy + hardening
- [ ] Neon (dev/prod branches), Render (2 services), Vercel; CD workflow; secrets
- [ ] Release `develop → main` v0.1.0; smoke test prod
- [ ] Edge cases, error messages, empty states; frontend tests

### Sun 04 Oct: Write-up + submit
- [ ] `README.md`: run, test, credentials, URLs, badges, screenshots, 5M-episodes section
- [ ] `NOTES.md`: all 6 sections (design, left out, what went wrong, security, scale, AI tooling)
- [ ] Clean-clone test on a fresh folder; final release; **email the link by 16:00**

### Cut list (if behind, cut from the top)
1. Frontend tests beyond login/guard
2. Analytics chart (show tables instead)
3. Dev environment (keep prod only)
4. SonarCloud
5. Deployment entirely (it's the stretch item; everything else is required)

---

## 13. Definition of done (per issue)

- Code + tests in the same PR; CI green; no new Sonar issues
- Migration included if models changed
- API change reflected in OpenAPI and, where relevant, in the UI
- Decision or trade-off noted in `PLAN.md` §14 (becomes NOTES.md)

## 14. Decision log (for NOTES.md)

| # | Decision | Reason |
|---|---|---|
| 1 | Unauthorised access to another client's request returns 404, not 403 | Don't reveal that it exists |
| 2 | Status history as append-only events table + current `status` column | Fast reads; full audit |
| 3 | One-active-assignment enforced by partial unique index | Correct under concurrency, not just in Python |
| 4 | Import: recording system is source of truth (upsert), except it can't break assignments | Idempotent and safe |
| 5 | Naive CSV timestamps = UTC; `DD/MM/YYYY` day-first | Stated assumption |
| 6 | Median uses first delivery | Rework doesn't hide slow first delivery |
| 7 | UUID for users/requests, bigint for episodes | Non-guessable URLs; compact high-volume index |
| 8 | JWT in memory + refresh in localStorage | Cross-domain deploy; XSS risk acknowledged, mitigated by CSP + short access TTL |
| 9 | One repository (monorepo) for backend and frontend | Brief asks for one repo and `docker compose up` from a clean clone; API + UI change in one PR; Render/Vercel deploy by root directory |
