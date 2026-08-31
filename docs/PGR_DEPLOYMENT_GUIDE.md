# PGR Platform — Deployment & Configuration Guide (for the infrastructure team)

**Audience:** infrastructure / DevOps engineers deploying to staging or production.
**Source of truth for settings:** `backend/app/core/config.py` (typed) and `backend/.env.example` (annotated). Everything below matches those files.

---

## 1. What you are deploying

Four processes plus a database. Nothing exotic: no Redis, no message broker, no object store is *required* (fields exist for later adoption).

| Component | What it is | Process | Port |
|---|---|---|---|
| **API** | FastAPI (Python), async SQLAlchemy | `uvicorn app.main:app` | 8000 (internal) |
| **Worker** | Background jobs: scheduler, outbox dispatch, email notifications | `python -m app.worker` | none |
| **Frontend** | Next.js 14, pre-built, served by `next start` | `npm run start` | 3000 (internal) |
| **Database** | PostgreSQL **16 or newer** (developed against 18) | managed service or VM | 5432 (private) |
| Reverse proxy | nginx / ALB / equivalent — the only public entry point | | 443 |

**Runtime requirements**
- Python **3.12+** (runs on 3.13). Dependencies: `backend/requirements.txt` — includes scikit-learn (used only by Pattern Lab model training; keep it unless you need a slim image).
- Node **18+** for building and serving the frontend.

---

## 1a. Hardware sizing (VMs, RAM, storage)

These numbers are grounded in measurements from the running system, not guesses: the full
database is **15 MB at 343 students including all ML artifacts** (≈45 KB/student), API read
p95 is 6 ms, Pattern Lab batch scoring of the whole cohort takes <1 s, and model training
bursts one CPU core for 30–60 s. This is a light workload — a PGR office is tens of
concurrent staff, not thousands of public users.

### Recommended VM configurations

| Tier | Use for | Layout | Specs |
|---|---|---|---|
| **Staging / pilot** (≤500 students, ≤25 concurrent users) | UAT, first go-live | **1 VM**, everything incl. Postgres | **2 vCPU · 4 GB RAM · 60 GB SSD** |
| **Production — standard** (≤3,000 students, ≤150 concurrent) | recommended | **2 VMs**: app (API+worker+frontend) / database | App: **2 vCPU · 4 GB · 40 GB** · DB: **2 vCPU · 8 GB · 100 GB SSD** |
| **Production — single-box** | when 2 VMs is not an option | 1 VM, all components | **4 vCPU · 16 GB RAM · 150 GB SSD** |
| **Large** (≥5,000 students or heavy analytics use) | rarely needed | as standard, larger DB | App: 4 vCPU · 8 GB · DB: 4 vCPU · 16 GB · 250 GB SSD |

OS: any current Linux LTS (Ubuntu 22.04/24.04, RHEL 9). No GPU — Pattern Lab is deliberately
CPU-only (scikit-learn at institutional scale).

### Where the RAM goes (steady state)

| Process | RAM | Notes |
|---|---|---|
| API (uvicorn) | 200–400 MB | ~+250 MB per extra uvicorn worker if you scale it |
| Worker | 150–250 MB | brief +300 MB burst during a Pattern Lab training run |
| Frontend (`next start`) | 200–400 MB | |
| PostgreSQL | give it **2–4 GB** (`shared_buffers` 1–2 GB, `effective_cache_size` ~50 % of the DB host's RAM) | the whole database fits in cache for years — memory is what makes it fast |
| OS + headroom | 1–2 GB | |

4 GB is genuinely enough for the app VM; the DB host is where extra RAM pays off.

### Where the disk goes

| Store | Size today | Growth | Plan for |
|---|---|---|---|
| PostgreSQL data | 15 MB @ 343 students | ~45 KB/student; ML predictions append ~0.3 MB per model per scoring batch | **< 5 GB even at 10,000 students** — provision 100 GB for WAL, indexes, temp and slack, not for data |
| `STORAGE_ROOT` (uploaded documents) | grows with use | the real driver: theses, reviews, evidence. Estimate **10–40 MB per student per year** (uploads capped at `MAX_UPLOAD_MB`=50) | 3,000 students × 3 years ≈ **90–250 GB** — size this volume, and put the backups here-sized too |
| Application code + venv + node_modules | ~2.5 GB | static | included in the 40 GB app disk |
| Logs | depends on retention | JSON on stdout — size by your log platform's retention, not local disk | ship, don't store locally |

Disk type: any SSD is fine (gp3 / Premium SSD / balanced PD). The database is small enough
that IOPS never becomes the bottleneck at this scale; **do not** pay for provisioned-IOPS tiers.

### CPU notes

- Steady state is near-idle; the measured p95s were achieved on a developer laptop.
- The only CPU bursts: Pattern Lab **training** (~1 core, 30–60 s, admin-triggered) and the
  statutory **CSV exports** (seconds). Neither justifies more cores; they just briefly use one.
- Scale trigger: if API latency ever matters, add uvicorn workers (`--workers 2–4`) or a second
  app VM behind the proxy **before** adding cores to one process — the app is I/O-bound, not CPU-bound.

### Network / misc

- Internal 1 Gbps is more than sufficient; API↔DB round trips are the only chatty path — keep
  the app and DB VMs in the same zone/subnet (<1 ms).
- Public bandwidth is trivial (dashboard JSON + occasional document download).
- Snapshots: nightly VM/disk snapshot of the DB host and the `STORAGE_ROOT` volume satisfies
  the backup baseline in §9.

- Disk: a **persistent volume** for `STORAGE_ROOT` (uploaded documents) and normal Postgres storage. Everything else is stateless.

---

## 2. Network topology (recommended)

```
Internet ── 443 ──> reverse proxy (TLS)
                       │
                       ├── /            ──> frontend  :3000
                       └── /api/v1/*    ──> API       :8000   (also /health/*)
                                              │
                       worker ────────────────┤  (same DATABASE_URL, no inbound port)
                                              ▼
                                        PostgreSQL :5432 (private subnet only)
```

Two valid ways to route API traffic — pick ONE:

**Option A (recommended): proxy routes `/api/v1` straight to the backend.**
The browser calls the same origin; nginx splits traffic. The frontend's own proxy is then never used, and `BACKEND_ORIGIN` does not matter.

**Option B: let Next.js proxy.** The frontend forwards `/api/v1/*` to the backend itself (`next.config.mjs` rewrite). ⚠️ **`BACKEND_ORIGIN` is baked in at `npm run build` time**, not read at runtime — if you use this option, export `BACKEND_ORIGIN=http://<api-host>:8000` **before building**, and rebuild whenever it changes.

Only the proxy is public. API, worker, frontend and Postgres live on private networks. The worker needs no inbound connectivity at all.

---

## 3. Backend configuration (environment variables)

Set via environment / secret manager. Local files use `backend/.env`; **never commit real values**. Full annotated list in `backend/.env.example`.

### 3.1 Must set in production

| Variable | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | |
| `APP_SECRET_KEY` | 32+ random bytes (e.g. `openssl rand -hex 32`) | Signs **JWTs** and is the **HMAC secret for inbound partner webhooks** (see §7). Rotating it invalidates all sessions and must be coordinated with integration partners. Store in a secret manager. |
| `DATABASE_URL` | `postgresql+asyncpg://<app_role>:<password>@<host>:5432/<db>` | Must be the `+asyncpg` driver. Use a dedicated **application role**, not a superuser. |
| `APP_BASE_URL` | `https://<public-hostname>` | Used to build links inside emails (password reset, notifications). Must be the public URL users see, not an internal one. |
| `EMAIL_BACKEND` | `smtp` | `console` (default) only logs emails — fine for staging, silent-failure in prod. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_USE_TLS` | your relay | Password in the secret manager. |
| `EMAIL_FROM` | `PGR Platform <no-reply@your-domain>` | The display-name half can later be changed by admins in-app (Settings → Email); the mailbox itself stays here in the environment, deliberately. |
| `STORAGE_ROOT` | e.g. `/var/lib/pgr/storage` | **Persistent volume.** Uploaded documents live here (`STORAGE_BACKEND=local`). Back it up alongside the database. |

### 3.2 Should review

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_REPLICA_URL` | unset | Optional read-replica DSN; read-only endpoints will use it when set. |
| `ACCESS_TOKEN_TTL_SECONDS` / `REFRESH_TOKEN_TTL_SECONDS` | 900 / 1209600 | 15 min access, 14 day refresh. |
| `MAX_FAILED_LOGINS` / `LOCKOUT_MINUTES` | 5 / 15 | Brute-force lockout. |
| `PASSWORD_RESET_TTL_SECONDS` | 3600 | Reset links are also how **new users are invited** — they set their own password; admins never handle one. |
| `MAX_UPLOAD_MB` | 50 | Match your proxy's `client_max_body_size`. |
| `WORKER_*_INTERVAL_SECONDS`, `OUTBOX_MAX_ATTEMPTS` | 60/20/30, 5 | Worker cadences; defaults are fine. |
| `LOG_LEVEL` | `info` | Logs are structured JSON on stdout — point your log shipper at process stdout. |
| `SENTRY_DSN`, `OTEL_EXPORTER_ENDPOINT` | unset | Optional error/trace export. |

### 3.3 Leave off unless the institution decides otherwise

| Variable | Default | Why it matters |
|---|---|---|
| `ASSISTANT_LLM_ENABLED` + `ANTHROPIC_API_KEY` | off / unset | The "Ask PGR" assistant is fully on-premise by default. Turning the LLM fallback on sends record content to a third-party API — a **GDPR decision, not an infra decision**. Even with a key present, it stays off unless enabled (env or in-app setting). |
| `OIDC_*` | unset | SSO placeholders; password auth is the current mechanism. |
| `REDIS_URL`, `BROKER_URL`, `OBJECT_STORE_*`, `STORAGE_BACKEND=s3`, `INTEGRATION_*_URL` | unset | Reserved for later adoption; nothing requires them today. |

> **Deliberate design note for infra:** runtime *business* tunables (supervision limits, email kill-switch, Pattern Lab task-raising, etc.) are **not** environment variables — administrators manage them in-app under **Settings**, stored in the database. The environment holds only infrastructure and secrets. You should never be asked to redeploy for a policy change.

---

## 4. Frontend configuration

- Build: `npm ci && npm run build` in `frontend/`. Serve: `npm run start` (listens on 3000).
- **Only one variable matters: `BACKEND_ORIGIN`** — and only if you chose Option B in §2, and only **at build time**.
- After every deploy of a new build, **restart** the `next start` process. Replacing `.next` under a running server serves stale chunk hashes (blank pages with 404s in the console).

---

## 5. Installation & database steps (first deploy)

```bash
# 1. Database (as postgres admin)
CREATE ROLE pgr_app LOGIN PASSWORD '<from-secret-manager>';
CREATE DATABASE pgr OWNER pgr_app;

# 2. Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-prod.txt   # production set: Postgres-only, no SQLite, no test tools
# environment set via your platform (or a .env file the service can read)

# 3. Schema — run on every deploy; migrations are additive and ordered
alembic upgrade head

# 4. Seed roles/permissions (idempotent — safe to run on every deploy)
python -m app.db.seed

# 5. Processes (see §6 for units)
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.worker            # exactly ONE instance — see below
cd ../frontend && npm ci && npm run build && npm run start
```

⚠️ **The seed creates demo accounts** (`admin@example.com/admin123`, plus a demo supervisor/student). In production either:
- change these passwords immediately after first login, **or**
- create the real administrator, then deactivate the demo accounts in **Settings → Users & roles**.
The seed's role/permission sync is required (new permissions ship with releases); the demo users are the only part needing cleanup.

**Every subsequent deploy:** `pip install -r requirements-prod.txt` → `alembic upgrade head` → `python -m app.db.seed` → restart API + worker → `npm ci && npm run build` → restart frontend.

---

## 6. Process supervision

Run each as a supervised service (systemd shown; translate to containers 1:1 — one container per row, same commands).

```ini
# /etc/systemd/system/pgr-api.service
[Service]
WorkingDirectory=/opt/pgr/backend
EnvironmentFile=/etc/pgr/backend.env
ExecStart=/opt/pgr/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

# /etc/systemd/system/pgr-worker.service   (exactly one instance!)
[Service]
WorkingDirectory=/opt/pgr/backend
EnvironmentFile=/etc/pgr/backend.env
ExecStart=/opt/pgr/backend/.venv/bin/python -m app.worker
Restart=always

# /etc/systemd/system/pgr-frontend.service
[Service]
WorkingDirectory=/opt/pgr/frontend
ExecStart=/usr/bin/npm run start
Restart=always
```

Rules that matter:

- **Exactly one worker.** Two workers double-process the notification queue and can double-send email. Scale the API horizontally if needed; never the worker.
- The API is async single-process; for more throughput add `--workers N` to uvicorn or run several instances behind the proxy — both are safe (all state is in Postgres).
- Health probes: `GET /health/live` (process up) and `GET /health/ready` (dependencies OK) on the API. Frontend probe: `GET /login` expecting 200.

---

## 7. Security checklist

- [ ] `APP_SECRET_KEY` is long, random, from a secret manager — it protects **both** user sessions (JWT) and inbound **webhook signatures** (partners HMAC-SHA256 the raw body with this same secret; see `docs/PGR_INTEGRATION_CONTRACT.md` before sharing anything with a partner).
- [ ] Postgres reachable **only** from API + worker hosts; app role is not superuser.
- [ ] TLS terminates at the proxy; HTTP redirects to HTTPS; HSTS on.
- [ ] Only the proxy is internet-facing. 8000/3000 are private.
- [ ] Demo seed accounts changed or deactivated (§5).
- [ ] `STORAGE_ROOT` volume is in the backup schedule with the database.
- [ ] SMTP credentials in the secret manager, not in unit files.
- [ ] `ASSISTANT_LLM_ENABLED` stays `false` unless the institution has made the data-sharing decision.
- [ ] Log shipping captures stdout of all three processes (structured JSON; each request carries a `requestId`).

---

## 8. Post-deploy verification (10 minutes)

1. `curl https://<host>/health/ready` → 200.
2. Log in at `https://<host>/login`; dashboard's "Platform connectivity" card shows API *reachable*, Database *ok*.
3. `alembic current` on the host shows the same revision as `alembic heads` in the repo.
4. Settings → Users & roles loads (proves permission seed).
5. Trigger a password reset from the login page → email arrives via your relay (proves SMTP + `APP_BASE_URL` link is correct).
6. Watch the worker log for one cycle (scheduler / dispatch / notify lines every 60/20/30 s).
7. If Pattern Lab is in use: Advanced → Pattern Lab loads; `pip show scikit-learn` on the API host confirms the ML extra.

---

## 9. Backup & recovery

- **Postgres**: continuous archiving or at minimum nightly `pg_dump`; the database holds *everything* except uploaded files — including audit trail, ML models (pickled artifacts are DB rows) and predictions.
- **`STORAGE_ROOT`**: file-level backup on the same schedule.
- Restore = restore DB + storage volume, redeploy code, `alembic upgrade head` (no-op if versions match), restart.

## 10. Known operational notes

- Windows dev scripts (`start-all.bat` etc.) are **development-only**; production is the process model above.
- A rebuilt frontend must be restarted (stale-chunk issue, §4).
- The worker is also the auto-return engine for student suspensions and the email dispatcher — if email "stops", check the worker service first.
- `docs/PGR_NON_FUNCTIONAL_CRITERIA.md` tracks the wider NFR posture (41 met / 4 partial / 10 not met — the unmet items are mostly this document's concerns: ops runbooks, TLS, backups. Deploying per this guide closes most of them.)
