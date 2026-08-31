# PGR Platform — Infrastructure Requirements (Bill of Materials)

**Purpose:** the complete list of everything the infrastructure team must provision to run the
PGR Platform in production (plus staging). Hand this over as the requisition; the *how* —
process layout, environment variables, install steps, verification — is in
`PGR_DEPLOYMENT_GUIDE.md`.

---

## 1. Compute (VMs)

| # | Item | Qty | Spec | Purpose |
|---|---|---|---|---|
| 1.1 | **Production app VM** | 1 | 2 vCPU · 4 GB RAM · 40 GB SSD · Ubuntu 22.04/24.04 LTS (or RHEL 9) | Runs API (uvicorn :8000), background worker, frontend (:3000) |
| 1.2 | **Production database VM** | 1 | 2 vCPU · 8 GB RAM · 100 GB SSD · same OS | PostgreSQL 16+ (skip if using managed Postgres — see 3.1) |
| 1.3 | **Staging VM** | 1 | 2 vCPU · 4 GB RAM · 60 GB SSD | Everything incl. Postgres on one box |
| 1.4 | Reverse proxy | — | on the app VM (nginx) **or** the org's existing LB/WAF | TLS termination, routing |

No GPU anywhere. Single-box production alternative: one VM at 4 vCPU · 16 GB · 150 GB SSD (items 1.1+1.2 merged).

## 2. Storage (volumes, beyond OS disks)

| # | Item | Size | Attached to | Purpose |
|---|---|---|---|---|
| 2.1 | **Documents volume** (`STORAGE_ROOT`) | **250 GB**, expandable | app VM | Uploaded files: theses, review evidence (grows 10–40 MB/student/yr — the only real growth) |
| 2.2 | Database data disk | included in 1.2 (100 GB SSD) | DB VM | DB is tiny (15 MB @ 343 students); disk is for WAL/indexes/slack |
| 2.3 | **Backup storage** | **500 GB** (≈ 2× data, 30-day retention) | backup target / object storage | Nightly DB dumps + documents-volume backup + config |
| 2.4 | Staging documents dir | included in 1.3 | staging VM | no separate volume needed |

Standard SSD tiers (gp3 / Premium SSD / balanced PD). Provisioned-IOPS tiers are unnecessary.

## 3. Database

| # | Item | Requirement |
|---|---|---|
| 3.1 | **PostgreSQL 16 or newer** | Either self-hosted on VM 1.2, **or** a managed instance (RDS/Azure Database/Cloud SQL — smallest production tier, 2 vCPU/8 GB, 100 GB). Managed is preferred if available: backups and patching come free |
| 3.2 | Databases | `pgr` (production), `pgr_staging` (staging) |
| 3.3 | Roles | `pgr_app` — LOGIN, owner of the `pgr` database, **not** superuser. One per environment |
| 3.4 | Extensions / special config | **None required.** Default config + `shared_buffers` 1–2 GB is all |

## 4. Network

| # | Item | Requirement |
|---|---|---|
| 4.1 | Subnets / segmentation | Public: proxy only. Private: app + DB. (One private subnet is fine; DB reachable only from app VM) |
| 4.2 | **Static public IP** | 1, on the proxy |
| 4.3 | **DNS records** | `pgr.<institution-domain>` → proxy IP (prod); `pgr-staging.<domain>` (staging) |
| 4.4 | **TLS certificate** | For both names — org CA, ACME/Let's Encrypt, or wildcard. Auto-renewal required |
| 4.5 | Firewall rules | See table below |

**Firewall matrix**

| From | To | Port | Purpose |
|---|---|---|---|
| Internet | proxy | 443 (80 redirect-only) | user traffic |
| proxy | app VM | 3000, 8000 | frontend, API |
| app VM | DB | 5432 | database |
| app VM | SMTP relay | 587 (or org standard) | outbound email |
| admin network / bastion | all VMs | 22 | SSH administration |
| app VM (optional, outbound) | api.anthropic.com:443 | only if the LLM assistant fallback is ever enabled | otherwise block outbound as policy dictates |
| partner systems (later) | proxy 443 (`/api/v1/integration/webhooks/*`) | inbound HR/Research webhooks — signed; nothing to open beyond 443 |

## 5. Email

| # | Item | Requirement |
|---|---|---|
| 5.1 | **SMTP relay account** | Host, port, username, password, STARTTLS — org relay or transactional provider |
| 5.2 | **Sender address** | e.g. `no-reply@<institution-domain>` |
| 5.3 | SPF / DKIM / DMARC | Authorise the relay for the sender domain — password-reset and invite emails must not land in spam |

## 6. Secrets (create in the org secret manager before deploy)

| # | Secret | Notes |
|---|---|---|
| 6.1 | `APP_SECRET_KEY` | 32+ random bytes per environment (`openssl rand -hex 32`). Signs sessions **and** partner webhook HMAC — rotation must be coordinated |
| 6.2 | DB password for `pgr_app` | per environment |
| 6.3 | SMTP password | |
| 6.4 | (optional) `ANTHROPIC_API_KEY` | only if the institution later approves the assistant's LLM fallback |

## 7. Software on the VMs (base image / bootstrap)

| # | Item | Version |
|---|---|---|
| 7.1 | Python | 3.12+ (3.13 fine) with venv |
| 7.2 | Node.js + npm | 18+ (LTS) |
| 7.3 | nginx | current stable (if proxy is on-VM) |
| 7.4 | PostgreSQL server | 16+ (only if self-hosting, VM 1.2) |
| 7.5 | Code delivery | git access to the repository, or an artifact pipeline — infra's choice |

## 8. Backup & recovery

| # | Item | Requirement |
|---|---|---|
| 8.1 | Database | Nightly `pg_dump` (or managed-service automated backups + PITR). Retention ≥ 30 days |
| 8.2 | Documents volume | Nightly file-level backup or volume snapshot, same retention |
| 8.3 | Restore test | One documented test restore before go-live |

## 9. Monitoring & logging

| # | Item | Requirement |
|---|---|---|
| 9.1 | Uptime probes | `GET /health/live` + `GET /health/ready` (API), `GET /login` (frontend), every 60 s, alert on failure |
| 9.2 | Log shipping | stdout of the 3 app processes (structured JSON) into the org log platform; retention per policy |
| 9.3 | Process supervision | systemd units (templates in the deployment guide) with `Restart=always`; alert on repeated restarts. **Worker must be a singleton** |
| 9.4 | Disk alerts | Documents volume ≥ 80 %, DB disk ≥ 80 % |
| 9.5 | (optional) Error/tracing | Sentry DSN and/or OTLP endpoint if the org runs them — supported via env vars, not required |

## 10. Access & people

| # | Item | Requirement |
|---|---|---|
| 10.1 | SSH access | via bastion/VPN for the deploying engineers |
| 10.2 | Deploy mechanism | infra's standard (CI runner, Ansible, or documented manual steps from the deployment guide) |
| 10.3 | First application admin | agree who receives the first real admin account (created in-app; demo seed accounts are then deactivated) |

## 11. Explicitly NOT needed (don't provision)

- ❌ Redis / message broker — config fields exist but nothing uses them yet
- ❌ S3 / object store — local volume backend is the current design
- ❌ GPU instances — Pattern Lab is CPU-only by design
- ❌ Kubernetes — three systemd services (or three containers) is the intended scale
- ❌ Read-replica database — supported (`DATABASE_REPLICA_URL`) but unnecessary at this load
- ❌ Provisioned-IOPS disks, CDN, cache tier

## 12. Decisions we need back from infra

1. Cloud/on-prem platform and region (I can convert §1 into exact instance SKUs once known).
2. Managed Postgres vs self-hosted (3.1)?
3. TLS certificate source (org CA vs ACME)?
4. SMTP relay details (5.1) and confirmation SPF/DKIM can be set for the sender domain.
5. Log platform to ship into (9.2).
6. DNS names confirmed (4.3).

---

**Quick totals — production:** 2 VMs (2 vCPU/4 GB + 2 vCPU/8 GB), 1 × 250 GB documents volume, 1 × 500 GB backup target, 1 public IP, 2 DNS names + certs, 1 SMTP account, 4 secrets, PostgreSQL 16+.
**Staging:** 1 VM (2 vCPU/4 GB/60 GB), 1 DNS name + cert, shares relay with a staging sender address.
