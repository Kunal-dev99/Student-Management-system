# Architecture Decision Log — PGR Platform

> Maintained by **solution-architect**. One entry per fork that shapes delivery.

## D-01 — Frontend runs on Next.js 14, not Vite
- **Status:** Accepted (2026-08-21, confirmed by product owner).
- **Context:** Arch §14.2/§14.3 *recommends* a Vite React SPA + React Router. The FP design
  system ("Redwood Professional") ships as a complete **Next.js 14 (App Router)** bundle —
  `app/layout.tsx` pre-hydration theme script, `next/font`, `next/image` logo route,
  `next/navigation` breadcrumbs.
- **Decision:** Build the frontend on **Next.js 14**, adopting the design bundle verbatim.
- **Why:** §14 says "recommended", not mandated. Next.js gives an exact, zero-port look match
  and preserves the theming/FOUC/logo-plate guarantees the bundle depends on. Porting to Vite
  would mean re-wiring fonts, image, and routing with no design payoff for the MVP.
- **Consequences:** Frontend still honours the §14 contract (all data via `/api/v1`, tokens in
  memory, `/api/v1/me` drives nav, types generated from OpenAPI). If SSR/edge concerns or a
  hard SPA requirement emerge later, revisit as D-01a (port tokens + shadcn to Vite).

## D-02 — Modular monolith first (from arch §2, §22)
- **Status:** Accepted (inherited from spec).
- **Decision:** One deployable FastAPI app, strict modules communicating via service
  interfaces + domain events, never shared tables. Extract to services later if a module
  needs independent scaling.

## D-03 — One person, many relationships (from arch §8.6, §22)
- **Status:** Accepted (inherited from spec).
- **Decision:** `person_id` is preserved across applicant → student → alumni/employee. Offer
  acceptance and graduation reuse the same person; they never create a new person record.

## D-04 — Develop on SQLite now, migrate to PostgreSQL later
- **Status:** Superseded 2026-08-21 — **PostgreSQL 18 installed and now the active dev DB.**
  App role `pgr` on database `pgr`, DSN in `backend/.env`. Switch validated end-to-end (migrations,
  seed, login, timeline). The SQLite default remains in `config.py` as a fallback for anyone without
  Postgres, and the test suite still runs on in-memory SQLite — so the portability rules below stay in force.
  One portability bug surfaced and was fixed during the switch: timestamp columns must be
  `DateTime(timezone=True)` (timestamptz) — asyncpg rejects tz-aware values into naive columns
  (SQLite tolerated it). Fixed in `db/base.py TimestampMixin` (arch §8.1).
- **Original status:** Accepted (2026-08-21, user decision — IT Postgres install delayed).
- **Context:** Arch §4 mandates PostgreSQL 16 for production. Installing it needs admin rights
  the dev box doesn't have (winget install blocked by UAC, `0x800704c7`). IT request is pending
  (see `docs/POSTGRES_IT_REQUEST.md`).
- **Decision:** Build Phase 1 against async **SQLite** (`sqlite+aiosqlite`, the config default).
  Switch to Postgres when IT provides it by changing `DATABASE_URL` in `backend/.env` and running
  `alembic upgrade head` — no code changes.
- **Consequences / rules to keep the switch cheap:**
  - Access the DB only through SQLAlchemy + Alembic — no raw SQL, no SQLite-specific pragmas in app code.
  - Keep models **portable**: UUIDs, enums, timestamps written so they work on both engines
    (SQLAlchemy maps UUID→text, Enum→varchar on SQLite automatically).
  - **Gate Postgres-only DDL** (JSONB indexes, table partitioning, materialized views, `citext`,
    trigger-based `updated_at`) behind a dialect check so migrations run on SQLite too, with the
    Postgres-only optimisations applied only when `settings.is_postgres`.
  - Phase 2/3 features that are inherently Postgres-only (partitioning §8.14, materialized views
    §13) require Postgres to be in place before they ship.
  - Test/dev rows in `pgr_dev.db` are disposable — re-seed on Postgres rather than copying, unless
    real data has accumulated (then a one-time `pgloader`/script copy).

<!-- Add new decisions below. Never renumber existing IDs. -->
