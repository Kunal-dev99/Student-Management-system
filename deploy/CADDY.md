# Deploying the PGR Platform behind Caddy

Caddy is the single HTTPS front door. It terminates TLS and splits traffic between the two app
processes:

```
Browser ──HTTPS──> Caddy ┬─ /api/*  /health/*  ─► FastAPI backend   (127.0.0.1:8001)
                         └─ everything else     ─► Next.js frontend (127.0.0.1:3000)
```

Because everything is one origin, the frontend's `/api/v1` calls are same-origin — **no CORS**.

## Prerequisites

- The backend and frontend already running (e.g. via `start-all.bat`, or as services).
- **Bind the backend to loopback in production.** Behind Caddy the API should not be exposed
  directly — change `start-backend.bat` (or your service) to `--host 127.0.0.1 --port 8001` so only
  Caddy can reach it. (`0.0.0.0` is only needed when nothing fronts it.)
- Caddy installed: <https://caddyserver.com/docs/install> (Windows: `choco install caddy` or the
  release zip; Linux: the official apt/yum repo).
- For public TLS: a DNS A/AAAA record for your domain pointing at the server, and inbound
  **80 + 443** open (Caddy needs 80 for the ACME HTTP challenge and to redirect to HTTPS).

## Run it

Production (public domain, automatic certificates):

```bash
# set the environment for your deployment
export PGR_DOMAIN=pgr.icr.ac.uk
export TLS_EMAIL=platform@icr.ac.uk
export PGR_BACKEND=127.0.0.1:8001      # change if your backend runs elsewhere
export PGR_FRONTEND=127.0.0.1:3000

caddy validate --config deploy/Caddyfile     # sanity-check first
caddy run      --config deploy/Caddyfile     # foreground; use a service for real deploys
```

Local HTTPS testing (no public domain, Caddy's internal CA):

```bash
caddy run --config deploy/Caddyfile.local    # https://localhost
```

## Running as a service

- **Linux (systemd):** install the packaged `caddy.service`, put this file at `/etc/caddy/Caddyfile`
  (or point the unit at `deploy/Caddyfile`), set the env vars in the unit or `/etc/default/caddy`,
  then `systemctl enable --now caddy`. Caddy stores/renews certs automatically.
- **Windows:** run Caddy as a service (e.g. with NSSM) pointing at `caddy run --config
  deploy\Caddyfile`, or run it in a console for a quick stand-up. Adjust the `log` path in the
  Caddyfile to a Windows path (e.g. `C:/caddy/logs/pgr-access.log`).

## TLS modes

- **Automatic public certs** (default in `Caddyfile`): Caddy gets & renews Let's Encrypt/ZeroSSL
  certificates for `PGR_DOMAIN`. Nothing else to do once DNS + ports are right. While testing,
  uncomment the `acme_ca` staging line in the Caddyfile to avoid rate limits.
- **Internal CA** (`Caddyfile.local`, `tls internal`): a locally-trusted cert for `localhost` —
  good for dev and demos, not for anything a browser off this machine must trust.
- **Your own cert:** replace the `reverse_proxy`-site TLS with `tls /path/cert.pem /path/key.pem`.

## Notes baked into the config

- **Uploads:** `request_body max_size 50MB` covers the cohort CSV import and document uploads; raise
  it if you store large thesis PDFs.
- **Health-gated upstream:** the API route active-health-checks `/health/ready`, so Caddy stops
  routing to a backend that can't reach its database.
- **Streaming & WebSockets:** SSE (Composer streaming) and WebSocket upgrades pass through
  `reverse_proxy` unchanged.
- **Security headers:** applied by Caddy on frontend responses; the backend keeps setting its own on
  API responses (so they aren't doubled).

## Gotcha from this environment

On Windows, port 8000/8001 can get stuck behind an orphaned socket after a hard kill (a dead PID
keeps the listener bound). That's a *backend-host* issue, unrelated to Caddy — if the backend can't
bind its port, free it (reboot, or `stop.bat`) before starting Caddy. Caddy just proxies to whatever
`PGR_BACKEND` points at.
