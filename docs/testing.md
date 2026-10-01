# Testing strategy

Each layer catches a different kind of problem, and each runs as early as its cost allows. The goal is that a
defect, vulnerability or performance regression is found on a pull request or on `develop`, never in production.

## Layers

| Layer | What it catches | Tool | Runs | Status |
|---|---|---|---|---|
| Unit | Logic errors in small, pure pieces: parsing, normalisation, transition rules, formatting | pytest | every PR | ✅ |
| Integration | Endpoints, permissions, transactions and database constraints working together, on real PostgreSQL | pytest-django, DRF API client | every PR | ✅ |
| Contract | The API drifting from its OpenAPI description | `spectacular --validate --fail-on-warn` | every PR | ✅ |
| API fuzzing | Crashes and schema violations from thousands of generated inputs, as every role | Schemathesis | every PR | #45 |
| Coverage gate | Untested code being merged | pytest-cov, fail under 90% | every PR | #45 |
| Query budgets | N+1 queries and other database performance bugs | `django_assert_max_num_queries` | every PR | #45 |
| Smoke | The system not starting, migrating, seeding or logging in from a clean checkout | `docker compose up --wait` + curl | every PR | ✅ |
| Static security | Insecure code patterns | Ruff Bandit rules, CodeQL | every PR | #42 |
| Dependencies | Known-vulnerable packages | Dependabot, pip-audit, npm audit | every PR, daily | ✅ / #42 |
| Code quality | Duplication, complexity, code smells, coverage on new code | SonarCloud | every PR | #17 |
| End-to-end | Broken user journeys in a real browser | Playwright against the compose stack | merge to `develop`, nightly | #46 |
| Accessibility | Screens that can't be used with assistive technology | axe (in Playwright) | merge to `develop`, nightly | #46 |
| Dynamic security | Missing headers, insecure cookies, common web vulnerabilities in the running app | OWASP ZAP baseline | merge to `develop`, nightly | #47 |
| Load | Slow endpoints or errors under concurrent use | k6 (p95 < 300 ms, errors < 1%) | merge to `develop`, nightly | #47 |

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

## Running them

```bash
docker compose run --rm api pytest          # unit + integration
docker compose run --rm api pytest --cov    # with coverage
```

The end-to-end, security and load suites are added by #46 and #47, with their commands here.
