# Data warehouse export

How an institution's data reaches its data warehouse or BI tools. There are two ways in. Both
publish the same catalogue, and both only ever contain that institution's data.

| | Scheduled files (publications) | Pull API (consumers) |
|---|---|---|
| Best for | Nightly or hourly loads into a warehouse (Snowflake, Azure, OCI ADW, BigQuery) | Systems that fetch on their own schedule or need a few objects |
| Format | Parquet (recommended) or CSV, plus `manifest.json` | JSON (or CSV) pages |
| Changes | First run full, then only what changed, plus deletions. A full refresh every N days | `changedSince=<time>`, plus a deletions endpoint |
| Where | OCI Object Storage / any S3-compatible bucket (or a local folder) | `https://<platform>/api/v1/warehouse/data/...` |
| Set up in | **Administration → Data warehouse** | the same page: **API consumers** |

The modelled-on products are Oracle BICC (published view objects plus incremental extracts to
object storage) and Workday RaaS (an authenticated pull API).

## 1. What is published (the catalogue)

24 objects, defined once in `backend/app/db/tenant_views.py` (`CATALOGUE`):
- **Student and person records:** students, people, lifecycle events (suspensions,
  withdrawals, HESA leaver reasons).
- **Dated history:** every dated history (status, programme, intensity, fee status, location,
  expected end, UOA and so on).
- **Taught records:** module enrolments and their status history.
- **Funding and supervision:** funding arrangements and sources, supervision.
- **Reference data:** programmes, modules and their versions, units of assessment, departments.

The same catalogue drives the per-institution reporting views (T3), so files, API and views
always agree. **Administration → Data warehouse → What is published** lists every column.

- **Key:** every object has a stable `id` (UUID). Upsert on it.
- **Change column:** every row carries `_changed_at`, the time it last changed. A database
  trigger stamps it on every update, including corrections to history rows.
- **Personal data:** off by default. The standard edition leaves out names, emails and
  free-text notes, and gives year of birth instead of date of birth. A publication or consumer
  gets the full edition only when an administrator switches personal data on. Personal columns
  are marked in Parquet field metadata (`personal=true`) and in the catalogue.

## 2. Scheduled files

```
<bucket>/<prefix>/<institution>/<publication>/<run time, UTC>/
    manifest.json
    student.parquet              rows changed in the window (all rows on a full run)
    student__deleted.parquet     ids deleted in the window (incremental runs only)
    ...
```

**Loading rules:**
1. Wait for `manifest.json`. It's written last, so a run is complete once it exists.
2. For each object in the manifest:
   - **full:** replace what you hold for that object with the files;
   - **incremental:** upsert the rows on `id`, then delete the ids in `<object>__deleted`.
3. Check each file's `sha256`, `bytes` and `rows` against the manifest.

Incremental windows overlap by 5 minutes, which covers transactions still committing at the
cut-off, so a row can appear in two runs. Upserting makes that harmless. A failed run doesn't
move anything forward; the next run retries from the same point.

**Schedule:** daily at a chosen UTC hour, or hourly. A full extract runs every N days (default
7) as a safety net. Changing a publication's objects or its personal-data setting starts again
with a full run.

## 3. Pull API

**1. Get a token** (OAuth 2.0 client credentials):

```http
POST /api/v1/warehouse/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=pgrw_...&client_secret=...
```

HTTP Basic (`client_id:client_secret`) is accepted too. Tokens last 15 minutes. Errors follow
RFC 6749: `invalid_client` (401) and `unsupported_grant_type` (400).

**2. Read:**

| Call | Returns |
|---|---|
| `GET /api/v1/warehouse/data/objects` | The objects this consumer may read, with columns and types |
| `GET /api/v1/warehouse/data/objects/{name}?changedSince=&limit=1000` | `{rows, windowTo, nextCursor}`. `limit` can be up to 5000; `format=csv` is also accepted |
| `GET /api/v1/warehouse/data/objects/{name}?cursor=...` | The next page |
| `GET /api/v1/warehouse/data/objects/{name}/deleted?changedSince=` | Ids deleted since then |

**Paging:**
1. The first page fixes the window end, `windowTo`.
2. Follow `nextCursor` until it's null.
3. Store `windowTo` and use it as `changedSince` next time. Rows at the boundary may repeat;
   upsert on `id`.
4. Omit `changedSince` to read everything.

**Security:**
- A consumer belongs to one institution and reads only its data. The token names the
  institution, and the database's row-level security enforces it.
- Consumer tokens don't work on the rest of the API, and user tokens don't work here.
- **Rotate** issues a new secret and stops the old one at once. **Revoke** stops the consumer's
  current tokens at once.
- The secret is shown once and only its hash is stored.
- The token endpoint is rate-limited.

## 4. Setting up the bucket (OCI Object Storage)

1. In OCI, create a bucket (for example `pgr-warehouse`) and a **Customer Secret Key** for a
   user with write access to it.
2. In `backend/.env` (never in code or chat):

   ```
   WAREHOUSE_TARGET=s3
   WAREHOUSE_S3_ENDPOINT=https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
   WAREHOUSE_S3_REGION=<region>
   WAREHOUSE_S3_BUCKET=pgr-warehouse
   WAREHOUSE_S3_ACCESS_KEY=<customer secret key id>
   WAREHOUSE_S3_SECRET_KEY=<customer secret key>
   WAREHOUSE_S3_PREFIX=            # optional folder inside the bucket
   ```

   The same settings work for AWS S3 or MinIO. Without them, files go to
   `WAREHOUSE_LOCAL_ROOT` (default `backend/var/warehouse`).
3. Make sure the worker is running (`start-worker.bat`, or the worker service). It checks for
   due publications every 5 minutes (`WORKER_WAREHOUSE_INTERVAL_SECONDS`).
4. Give each institution's warehouse team read access to its own prefix only
   (`<prefix>/<institution>/`). Keys are laid out so a bucket policy can do that.

## 5. Where it lives in the code

| Piece | File |
|---|---|
| Catalogue (contract) | `backend/app/db/tenant_views.py`, `backend/app/modules/warehouse/catalogue.py` |
| Extract (windows, keyset paging, deletions) | `backend/app/modules/warehouse/extract.py` |
| Files and manifest | `backend/app/modules/warehouse/files.py`, `publish.py` |
| Targets (local, S3/OCI) | `backend/app/modules/warehouse/targets.py` |
| Publications, runs, watermarks | `backend/app/modules/warehouse/service.py`, `router.py` |
| Consumers, OAuth, pull API | `backend/app/modules/warehouse/pull.py` |
| Change tracking (triggers, delete log) | migration `w1_warehouse` |
| Admin screen | `frontend/src/app/(app)/warehouse/page.tsx` |

**Adding an object to the catalogue:** a new object needs a migration that adds the two
triggers (`pgr_touch_updated_at`, `pgr_log_deleted_row`) to its table.
`tests/integration/test_warehouse_tracking.py` fails until it has them.
