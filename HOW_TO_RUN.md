# How to run / test the PGR Platform (Windows)

Double-click these `.bat` files in the project root.

| File | What it does |
|---|---|
| **`setup.bat`** | One-time: creates the backend venv, installs deps, runs migrations, **seeds the demo login + sample data**, and builds the frontend. Run once (safe to re-run). |
| **`start-all.bat`** | Ensures **PostgreSQL** is running, then launches backend (:8000) + frontend (:3000, production) in two windows, then opens http://localhost:3000. **This is the one to use.** |
| `start-postgres.bat` | Ensures just the PostgreSQL service (`postgresql-x64-18`) is running. |
| `start-backend.bat` | Backend API only → http://localhost:8000 (`/api/v1/docs`). |
| `start-frontend.bat` | Frontend only (production build) → http://localhost:3000. |
| `dev-frontend.bat` | Frontend in dev/hot-reload mode — for editing UI. May be flaky on OneDrive (see note below). |
| **`test.bat`** | Backend tests (`pytest`) + frontend build, prints PASS/FAIL. |
| **`stop.bat`** | Kills whatever is on ports 8000 and 3000. |

## Login
After `setup.bat`, sign in with:

> **admin@example.com** / **admin123**

You'll land on the dashboard (shows you signed in, role, and live backend status), and can browse
**Persons** → click **Aisha Khan** to see the person-360 lifecycle timeline (applicant → student → alumni).

## First time
1. Double-click **`setup.bat`** and wait (frontend install + build takes a few minutes).
2. Double-click **`start-all.bat`**.
3. Browser opens → sign in with the demo login above.

## After the first time
Just **`start-all.bat`**. Stop with **`stop.bat`** or by closing the two windows.

## Notes
- Requires **Python** and **Node.js** on PATH (both already present on this machine).
- Backend runs on **PostgreSQL 18** (service `postgresql-x64-18`, database `pgr`), configured in
  `backend/.env`. `start-all.bat` makes sure the service is running first. The service is set to
  auto-start with Windows, so it's usually already up; if it ever needs starting and that fails,
  run `net start postgresql-x64-18` from an **admin** terminal. (Config still falls back to SQLite
  if `.env` is removed — see `docs/DECISIONS.md` D-04.)
- **Why the frontend runs in production mode:** this project lives in a **OneDrive** folder, and
  Next.js *dev* mode (hot reload) can corrupt its build cache on synced folders (`Cannot find module
  './xxx.js'`). `start-frontend.bat` runs the stable production server instead. Use `dev-frontend.bat`
  only while editing UI; if it breaks, stop it, delete `frontend\.next`, and restart.
- **After changing frontend code**, rebuild: `cd frontend && npm run build`, then `start-all.bat`.
