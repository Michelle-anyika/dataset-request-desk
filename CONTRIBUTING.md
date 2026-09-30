# Contributing

## Branches (git flow)

```
feat/*  fix/*  chore/* ... ──PR──► develop ──PR──► main
                                     ▲               │
                                     └── back-merge ─┤
                             hotfix/* ──PR───────────┘
```

| Branch | Purpose | Branches from | Merges into |
|---|---|---|---|
| `main` | Production | – | – |
| `develop` | Integration / dev environment | `main` | `main` (release PR) |
| `feat/<slug>` | New functionality | `develop` | `develop` |
| `fix/<slug>` | Bug fix found before release | `develop` | `develop` |
| `hotfix/<slug>` | Urgent fix for production | `main` | `main`, then `main → develop` back-merge |
| `chore/<slug>` | Tooling, config, dependencies | `develop` | `develop` |
| `docs/<slug>` `test/<slug>` `refactor/<slug>` `perf/<slug>` `ci/<slug>` `build/<slug>` | Same as the commit type | `develop` | `develop` |

`<slug>` is lower-case kebab-case, starting with the issue number when there is one:
`feat/12-status-transitions`, `fix/31-import-date-parsing`, `hotfix/token-expiry`.

**Enforced in two places:**
- locally, the `no-commit-to-branch` pre-commit hook refuses commits on `main`, `develop` or a misnamed branch;
- in CI, the **Branch naming** check fails a PR whose source branch isn't allowed for its target
  (into `develop`: the work prefixes above, `hotfix/*` or `main`; into `main`: `develop` or `hotfix/*`).

`develop` is the default branch: clones, new branches and PRs start there. `main` changes only on a release
or hotfix.

Keep branches short-lived and delete them after merge.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org), enforced by commitlint (`commitlint.config.mjs`)
locally and in CI.

```
<type>(<scope>): <subject in lower case, imperative, no full stop>

<optional body: what and why>

<optional footer: Closes #12>
```

**Types:** `feat` `fix` `refactor` `perf` `test` `docs` `style` `build` `ci` `chore` `revert`

**Scopes (optional):** `auth` `users` `requests` `episodes` `import` `assignments` `analytics` `api` `core` `db`
`ui` `backend` `frontend` `docker` `ci` `cd` `deps` `deps-dev` `release`

```
feat(requests): enforce allowed status transitions
test(import): cover idempotent re-import of the same file
fix(assignments): reject bad-quality episodes
ci: add commit message linting
```

## Test-driven development

Domain logic is written test-first, and the history shows it:

1. **Red:** `test(requests): reject delivery below requested episode count` (test fails)
2. **Green:** `feat(requests): block delivery until enough episodes are assigned` (minimum code to pass)
3. **Refactor:** `refactor(requests): extract transition rules into a table` (tests still green)

TDD applies to domain rules, permissions, the CSV import, analytics queries and API contracts. Scaffolding,
configuration and visual styling are not test-driven. A red commit may exist inside a PR, but the PR must be green
before merge.

## Pull requests

- Title follows the commit format. It becomes the merge commit title.
- Fill in the template, link the issue (`Closes #12`), keep it focused on one change.
- Required checks: CI OK, Conventional commits, Branch naming.
- PRs are merged with a **merge commit** (not squash), so the red → green → refactor commits stay in history.

## Local setup

```bash
pip install pre-commit
pre-commit install        # installs pre-commit and commit-msg hooks
```

Hooks check whitespace, YAML, merge markers, large files, private keys, the branch name and the commit message.
