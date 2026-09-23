# Runbook — restore or repair a single tenant (shared/pooled database)

All tenants share one database (`pgr`) and every tenant-owned row carries `tenant_id`, so
day-to-day per-tenant work is a `WHERE tenant_id = …` filter (see `scripts/tenant_ops.py`).
The one operation the pool makes harder is **rolling a single tenant back to an earlier
state**, because backups are whole-database. This runbook covers that safely.

Primary keys are UUIDs, so restored rows keep their original ids — no sequence fix-ups, and
no risk of colliding with another tenant.

---

## 0. Before you touch production

```bash
# A fresh, verifiable export of the tenant's CURRENT state — your safety net + an audit
# artifact. Keep it even if you think the data is already gone.
python -m scripts.tenant_ops export <tenant> --out ./var/tenant_exports
python -m scripts.tenant_ops stats  <tenant>      # note the row counts
```

Decide which case you are in:

- **Case A — bad data, rows still present** (a botched import corrupted values). You will
  overwrite the tenant's rows with a good copy.
- **Case B — rows were deleted** (accidental delete / cascade). You will re-insert them.

Either way the fix is: get a good copy from a backup into a scratch database, then move
**only that tenant's rows** back.

---

## 1. Restore the backup into a SCRATCH database

Do this as a superuser / DBA. Never restore over production.

```bash
# from a logical backup (pg_dump custom format)
createdb pgr_restore
pg_restore -d pgr_restore --no-owner --jobs 4 /backups/pgr-2026-09-22.dump

# ...or from a plain SQL dump
createdb pgr_restore && psql -d pgr_restore -f /backups/pgr-2026-09-22.sql
```

For point-in-time recovery (WAL archiving / a managed provider's PITR), restore the cluster
to the target timestamp into a **separate instance**, then treat it as `pgr_restore` below.

Sanity-check the tenant in the scratch copy before going further:

```bash
psql -d pgr_restore -c "SELECT count(*) FROM student  s JOIN tenant t ON s.tenant_id=t.id WHERE t.subdomain='<tenant>';"
psql -d pgr_restore -c "SELECT count(*) FROM person   p JOIN tenant t ON p.tenant_id=t.id WHERE t.subdomain='<tenant>';"
```

---

## 2. Find the tenant id and the table order

```bash
# tenant id (same value in both databases)
psql -d pgr_restore -tAc "SELECT id FROM tenant WHERE subdomain='<tenant>';"
```

Rows must move **parents first** (the reverse of delete order). Get a valid insertion order
straight from the schema — parents (referenced) before children (referencing):

```sql
-- run in either DB; prints tenant tables in a safe INSERT order
WITH fk AS (
  SELECT tc.table_name AS child, ccu.table_name AS parent
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name
  JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name
  WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'
), tt AS (
  SELECT table_name FROM information_schema.columns
  WHERE column_name='tenant_id' AND table_schema='public'
)
SELECT table_name FROM tt;  -- then order by fk depth, or reuse scripts/tenant_ops _delete_order and REVERSE it
```

In practice the reliable order is: **`tenant_ops` delete order, reversed.** `person`,
`programme`, `department`, `users` first; leaf tables (`assessment_result`, `milestone`,
`audit_log`, …) last.

---

## 3A. Case A — overwrite corrupted rows

Clear the tenant's current (bad) rows in production, then copy the good rows over. The
delete is tenant-scoped and transactional; it cannot touch any other tenant.

```bash
# 1) remove the tenant's current rows from production (dry-run first!)
python -m scripts.tenant_ops delete <tenant>          # DRY RUN — check the counts
python -m scripts.tenant_ops delete <tenant> --yes    # commit

# 2) stream each table's tenant rows from the scratch DB into production, PARENTS FIRST.
#    Repeat this line per table in insertion order.
psql -d pgr_restore -c "\copy (SELECT * FROM person WHERE tenant_id='<TID>') TO STDOUT" \
  | psql -d pgr -c "\copy person FROM STDIN"
psql -d pgr_restore -c "\copy (SELECT * FROM programme WHERE tenant_id='<TID>') TO STDOUT" \
  | psql -d pgr -c "\copy programme FROM STDIN"
# ... department, users, then the rest in insertion order ...
```

Wrap the production side in a transaction if you script it (`psql -1 -f copy_back.sql`) so a
mistake rolls back cleanly.

## 3B. Case B — re-insert deleted rows

The tenant's rows are gone from production, so there is nothing to delete — just run the
`\copy … FROM STDIN` step from 3A, parents first. Because ids are UUIDs and unchanged, all
foreign keys line up exactly as before.

If some rows still exist (a partial delete), add `ON CONFLICT DO NOTHING` by importing into a
staging table first, or clear the tenant with `tenant_ops delete` and do a clean re-insert.

---

## 4. Verify, then clean up

```bash
python -m scripts.tenant_ops stats <tenant>     # counts match the pre-incident numbers?
```

- Log in to the app on the tenant's subdomain and spot-check a few records.
- Confirm **other tenants are untouched**: `SELECT count(*) FROM person;` should equal the
  pre-restore total minus/plus only this tenant's delta.

```bash
dropdb pgr_restore     # remove the scratch database
```

---

## Notes and guardrails

- **Only this tenant moves.** Every SELECT/COPY is filtered by `tenant_id`, and the app's
  RLS gives a second layer if you run the app-role connection. You cannot accidentally pull
  another tenant's rows.
- **Global tables are shared and are NOT restored per-tenant** (`tenant`, `permission`,
  `role`, the auth-token tables, national HESA spec tables). If a restore must revive a
  deleted *user*, re-insert into `users` (parents first) before the tenant's rows that
  reference it; auth tokens can simply be re-issued by the user logging in again.
- **This need is the main reason to offer an enterprise "own database" (silo) tier** — a
  siloed tenant is restored by restoring its own database, no extraction dance. See
  `deploy/MULTI_TENANCY.md`.
- **Practice it once** on a staging copy before you need it for real.
