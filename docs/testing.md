# Testing strategy

Each layer catches a different kind of problem, and each runs as early as its cost allows. The goal is that a
defect, vulnerability or performance regression is found on a pull request or on `develop`, never in production.

## Layers

| Layer | What it catches | Tool | Runs | Status |
|---|---|---|---|---|
| Unit | Logic errors in small, pure pieces: parsing, normalisation, transition rules, formatting | pytest | every PR | ✅ |
| Integration | Endpoints, permissions, transactions and database constraints working together, on real PostgreSQL | pytest-django, DRF API client | every PR | ✅ |
| Contract | The API drifting from its OpenAPI description | `spectacular --validate --fail-on-warn` | every PR | ✅ |
| API fuzzing | Crashes, undocumented responses and accepted invalid input, from thousands of generated requests | Schemathesis, against the production-mode stack | every PR | ✅ |
| Coverage gate | Untested code being merged | pytest-cov, branch coverage, fail under 95% | every PR | ✅ |
| Query budgets | N+1 queries and other database performance bugs | `django_assert_max_num_queries` | every PR | ✅ |
| Smoke | The system not starting, migrating, seeding or logging in from a clean checkout | `docker compose up --wait` + curl | every PR | ✅ |
| Static security | Insecure code patterns | Ruff Bandit rules (`S`), CodeQL (`security-extended`, Python and workflows) | every PR, weekly | ✅ |
| Dependencies | Known-vulnerable packages | Dependabot, `pip-audit` on every lock file, `npm audit` | every PR, daily | ✅ |
| Code quality | Duplication, complexity, code smells, coverage on new code | SonarCloud quality gate | every PR | ✅ |
| End-to-end | Broken user journeys in a real browser: submit → start → assign → deliver → notify → accept, imports, analytics, accounts, role boundaries | Playwright against the compose stack | every PR | ✅ |
| Accessibility | Screens that can't be used with assistive technology (no serious or critical WCAG 2.1 AA violation) | axe on every screen the journeys visit | every PR | ✅ |
| Dynamic security | Missing headers, insecure cookies, common web vulnerabilities in the running app | OWASP ZAP baseline | merge to `develop`, nightly | #47 |
| Load | Slow endpoints or errors under concurrent use | k6: 10,000 requests from 200 users ([results](performance.md)) | on demand; nightly: #47 | ✅ |

## Gates

```
pull request ──► develop ──────────────► release PR ──► main (production)
   │                │                        │
   fast checks      slow checks              only if the latest
   (minutes):       (on merge and nightly):  develop run is green
   unit, integration,  end-to-end, axe,
   fuzzing, gates,     ZAP, k6
   SAST, deps, Sonar
```

- **Pull request:** nothing merges unless the fast checks pass (branch protection).
- **`develop`:** the slow checks run against the full Docker stack. A failure is fixed on `develop` before anything
  else is released.
- **Release:** a `develop → main` PR is merged only when the latest slow-check run on `develop` passed.

## What the tests prioritise

The brief names four areas, and they get the deepest tests:

1. **Authorization:** a role × endpoint matrix, and every client trying every other client's data.
2. **Status transitions:** every valid move for the right role, every invalid pair, wrong roles, guards.
3. **Assignment rules:** quality, one active request per episode (including the database constraint), locking.
4. **Import idempotency:** every messy case in `seed/episodes.csv`, and the same file imported twice.

## How we write tests

- **Test-first** for domain rules: a failing `test(...)` commit, then the `feat(...)` that passes it
  ([CONTRIBUTING.md](../CONTRIBUTING.md)).
- **Real PostgreSQL** for anything touching the database: the rules rely on Postgres features (partial unique
  indexes, `SELECT … FOR UPDATE`, `percentile_cont`), and a different database would hide real bugs.
- **Behaviour, not implementation:** tests call the API or a service and check results, so refactoring doesn't break
  them. For example, the switch from a revocation timestamp to a session version kept every session test unchanged.
- **One reason to fail per test**, named after the rule it protects.

## Coverage

**99.7 % of lines and branches** (476 tests). CI fails below **95 %**. That is not 100 %, on purpose:

- **Tested on purpose:** the paths that only run on a bad day. For example: a cache computation whose worker
  died, a Django 404/403 raised outside DRF, an unexpected crash (which must reveal nothing), an import the
  `csv` module cannot read, a refresh token whose server record is gone. They are collected in
  `tests/test_failure_paths.py`.
- **Excluded on purpose:** `__str__` methods (display only, in the admin and shell) and `TYPE_CHECKING`
  imports. The list is in `pyproject.toml` for anyone to check.
- **Why not 100 %:** at 100 %, the last few percent are usually tests written to touch a line, or
  `# pragma: no cover` comments. Coverage shows that code ran, not that it was checked; the fuzzer and the
  assertions do the checking. The 95 % gate catches a PR that adds untested code.

## Fuzzing

[Schemathesis](https://schemathesis.readthedocs.io/) reads the OpenAPI schema and sends about **2,600 generated
requests**: valid ones, invalid ones, boundary values, odd encodings and multi-step sequences. It runs against
the stack in production mode (`DJANGO_DEBUG=false`) as the seeded admin. It fails on any 500, any status, header
or body the schema doesn't describe, and any invalid input the API accepts. Configuration and the reasons for
each exception: [`fuzz/schemathesis.toml`](../fuzz/schemathesis.toml).

The first run found **23 problems**, all fixed and covered by tests:

| Found | Fix |
|---|---|
| A URL matching no route (e.g. `/api/requests/0.5/`) answered with Django's HTML page | JSON 400/403/404/500 handlers (`tests/test_error_pages.py`) |
| `?stauts=delivered` (a typo), `?status=` or a repeated filter were silently ignored: 200, unfiltered | Strict query parameters: unknown, blank or repeated is a 400 (`tests/test_query_params.py`) |
| `?unread=null` was read as "all"; `page_size=0` or `500` silently became 25 or 100 | `true`/`false` only; `page_size` must be 1-100 |
| The schema didn't state the `Idempotency-Key` format or the pagination bounds | Documented, so clients and the fuzzer know them |
| The analytics dates were documented as UTC (they are Kigali business dates since #66) | Corrected |

Now: **2,575 generated requests, 0 failures.** In 1,749 malformed requests on the first run, there was not one 500.

## Running them

```bash
docker compose run --rm api pytest          # unit + integration
docker compose run --rm api pytest --cov    # with coverage (fails under 95 %)

# Fuzzing, against the stack in production mode:
DJANGO_DEBUG=false THROTTLE_ANON_RATE=1000000/min THROTTLE_USER_RATE=1000000/hour docker compose up -d --wait
sh fuzz/run.sh                              # report in fuzz/report/

# Load test: see docs/performance.md

# Browser journeys with accessibility checks, against the stack (signs in often, so lift the login limit):
THROTTLE_LOGIN_RATE=1000/min docker compose up -d --wait
cd frontend && npx playwright install chromium && npm run e2e

# Frontend unit and component tests
cd frontend && npm test
```

**What the browser tests found** before any user did:
- **Contrast:** Mantine's dimmed text (3.3:1) and the text of light badges (as low as 1.7:1) were below WCAG AA's 4.5:1. They now pass, with colours measured against the badges' own backgrounds (`frontend/src/theme.ts`).
- **Names and roles:** toast and dialog close buttons had no accessible name, and the bell's popup attributes sat on a `<div>` instead of its button.
- **A sign-out bug:** after an admin signed out of `/users`, the next person to sign in, a client, was sent to `/users` and saw "Page not found". A sign-out now forgets the previous user's page; an expired session still returns you to yours.

The dynamic security suite (ZAP) is added by #47, with its command here.
