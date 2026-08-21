# PGR Platform — Backend

FastAPI + SQLAlchemy 2.0 async + PostgreSQL, modular monolith per
`PGR_Platform_Technical_Architecture.pdf`. Built by the `backend-engineer` agent from
tasks in [`docs/PGR_DELIVERY_PLAN.md`](../docs/PGR_DELIVERY_PLAN.md).

## Database

Active DB is **PostgreSQL 18** (local), configured in `backend/.env`:
`DATABASE_URL=postgresql+asyncpg://pgr:pgr_dev_pw@localhost:5432/pgr`.
To fall back to zero-setup SQLite, delete/rename `.env` (config defaults to
`sqlite+aiosqlite:///./pgr_dev.db`) and re-run `alembic upgrade head` + `python -m app.db.seed`.
The test suite always runs on in-memory SQLite, so code stays portable (decision D-04).

## Run locally

The app reads `DATABASE_URL` from `.env` (Postgres) or falls back to SQLite if absent.

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

./.venv/Scripts/alembic.exe upgrade head        # apply migrations
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- Liveness: `GET http://localhost:8000/health/live` → `{"status":"live"}`
- Readiness: `GET http://localhost:8000/health/ready` → checks the database
- OpenAPI: `http://localhost:8000/api/v1/openapi.json` · Docs: `/api/v1/docs`

## Run with the full stack (Postgres + Redis)

Requires Docker (not installed in the current dev box):

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

Set `DATABASE_URL=postgresql+asyncpg://pgr:pgr@localhost:5432/pgr` in `.env` for production-like runs.

## Tests

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest -q
```

## Layout (arch §5)

`app/core/` cross-cutting (config, database, errors, middleware, logging, pagination) ·
`app/db/` declarative base + Alembic · `app/api/v1/routes.py` aggregates module routers ·
`app/modules/<name>/` uniform 7-file domain modules (added in Phase 1) ·
`app/workers/` background tier (Phase 2).
