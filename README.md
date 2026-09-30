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

This starts PostgreSQL, applies database migrations and runs the API on <http://localhost:8000>.
No `.env` file is needed: every setting has a local default. To override one, copy `.env.example` to `.env`.

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

## Configuration

All configuration is read from environment variables; `.env.example` lists each one. Missing required values
(`DJANGO_SECRET_KEY`, `DATABASE_URL`) stop the app at startup with a clear error.

## Contributing

Branch naming, commit format and the TDD workflow are described in [CONTRIBUTING.md](CONTRIBUTING.md).
