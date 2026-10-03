"""T3 — the tenant view layer: one read-only "virtual database" per institution.

Reporting tools and data-warehouse loaders never touch the core tables. Each institution gets
two schemas of plain SQL views, generated from the catalogue below (never hand-written):

  tenant_<sub>        the standard set: no names, emails or dates of birth
                      (date of birth is published as year of birth only), no free-text notes;
  tenant_<sub>_full   the same objects with personal data, granted only when the institution
                      asks for it.

Every view has the institution's id baked in (``WHERE tenant_id = '<uuid>'``) and is a
``security_barrier`` view, so a reporting user's own filter functions can't run before it.
Underneath, row-level security still applies: the views are owned by ``pgr_views``, a NOLOGIN
role that is not the table owner, so it only gets the fail-closed policy, and each reporting
login is pinned to its institution (``app.current_tenant`` set on the role). Two locks: a
login that changes its own tenant setting still sees only its own rows through the views, and
it has no privileges on the core tables at all.

Rebuilt by every migration (dropped before, rebuilt after, so migrations can still alter
columns) and by ``scripts/tenant_reporting.py``. Postgres only.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text

logger = logging.getLogger("pgr.tenant_views")

VIEW_OWNER = "pgr_views"
_MARKER = "pgr tenant views"     # COMMENT on every schema we create; only those are ever dropped


@dataclass(frozen=True)
class Published:
    """One object in the published catalogue: a view over one core table."""
    name: str                                     # view name inside the tenant schema
    table: str                                    # source table in public
    description: str
    columns: tuple[str, ...]                      # in both schemas
    personal: tuple[str, ...] = ()                # full-detail schema only
    derived: tuple[tuple[str, str], ...] = field(default=())  # standard schema only: (name, SQL)


# Effective-dated history tables share one shape. `reason` is free text, so full detail only.
_DATED = ("valid_from", "valid_to", "origin", "recorded_at", "closure", "superseded_by", "source_event_id")


def _history(name: str, table: str, key: str, value: str, what: str) -> Published:
    return Published(name, table, f"Dated history of {what}: one row per period (valid_from, valid_to).",
                     ("id", key, value) + _DATED, personal=("reason",))


CATALOGUE: tuple[Published, ...] = (
    Published(
        "person", "person", "People (students, supervisors). Standard view: no names, email or date of birth.",
        ("id", "nationality", "uoa_id", "pseudonymised_at", "created_at", "updated_at"),
        personal=("external_person_ref", "given_name", "family_name", "preferred_name", "date_of_birth", "email"),
        derived=(("birth_year", "EXTRACT(YEAR FROM date_of_birth)::int"),),
    ),
    Published(
        "student", "student", "Student records, including the HESA engagement fields.",
        ("id", "person_id", "student_ref", "programme_id", "department_id", "research_area_id", "start_date",
         "expected_end_date", "original_expected_end_date", "study_mode", "status", "registration_status",
         "fee_status", "study_location", "fee_eligibility", "primarily_outside_uk", "study_intention",
         "incoming_exchange", "uoa_id", "created_at", "updated_at"),
    ),
    Published(
        "lifecycle_event", "student_lifecycle_event",
        "Suspensions, extensions, mode and programme changes, withdrawals and leavers (HESA leaver reason).",
        ("id", "student_id", "event_type", "status", "start_date", "end_date", "actual_end_date",
         "extension_days", "previous_mode", "new_mode", "previous_intensity_pct", "intensity_pct",
         "previous_programme_id", "new_programme_id", "effective_date", "leave_category", "leaver_reason",
         "days_applied", "decided_at", "created_at"),
        personal=("reason", "decision_note"),
    ),
    _history("status_period", "student_status_history", "student_id", "status", "student status"),
    _history("programme_period", "student_programme_history", "student_id", "programme_id", "programme"),
    _history("intensity_period", "student_intensity_history", "student_id", "intensity_pct", "study intensity (FTE %)"),
    _history("fee_status_period", "student_fee_status_history", "student_id", "fee_status", "fee status"),
    _history("location_period", "student_location_history", "student_id", "study_location", "study location"),
    _history("expected_end_period", "student_expected_end_history", "student_id", "expected_end_date",
             "expected end date"),
    _history("fee_eligibility_period", "student_fee_eligibility_history", "student_id", "fee_eligibility",
             "fee eligibility"),
    _history("outside_uk_period", "student_outside_uk_history", "student_id", "primarily_outside_uk",
             "study primarily outside the UK"),
    _history("student_uoa_period", "student_uoa_history", "student_id", "uoa_id", "a student's unit of assessment"),
    _history("person_uoa_period", "person_uoa_history", "person_id", "uoa_id", "a person's unit of assessment"),
    Published(
        "module_enrolment", "module_enrolment", "Module enrolments and results.",
        ("id", "student_id", "module_id", "academic_year", "module_run_id", "start_date", "end_date", "status",
         "final_mark", "outcome", "credits_awarded", "condoned", "created_at", "updated_at"),
    ),
    _history("module_enrolment_status_period", "module_enrolment_status_history", "module_enrolment_id",
             "status", "module enrolment status"),
    Published(
        "funding_arrangement", "funding_arrangement", "Funding arrangements (stipends, fees, sponsors).",
        ("id", "student_id", "funding_type", "funding_source_id", "stipend_amount", "currency", "valid_from",
         "valid_to", "ended_at", "status", "cost_centre", "project_code", "funder_reference",
         "research_award_id", "contribution_pct", "payment_frequency", "created_at", "updated_at"),
    ),
    Published("funding_source", "funding_source", "Funders.", ("id", "name", "funder_type")),
    Published(
        "supervision", "supervisor_relationship", "Supervisory relationships, dated, with weighting.",
        ("id", "student_id", "supervisor_person_id", "role", "status", "valid_from", "valid_to", "ended_at",
         "weighting_pct"),
        personal=("end_reason",),
    ),
    Published(
        "programme", "programme", "Programmes.",
        ("id", "name", "code", "department_id", "programme_type", "taught_total_credits", "duration_months"),
    ),
    Published(
        "programme_version", "programme_version", "Programme versions, dated.",
        ("id", "programme_id", "version_no", "valid_from", "valid_to", "taught_total_credits", "duration_months"),
    ),
    Published(
        "module", "taught_module", "Taught modules.",
        ("id", "programme_id", "code", "title", "credits", "term", "fte_pct", "level", "is_core"),
    ),
    Published(
        "module_version", "module_version", "Module versions, dated.",
        ("id", "module_id", "version_no", "title", "credits", "level", "term", "fte_pct", "valid_from", "valid_to"),
    ),
    Published("unit_of_assessment", "unit_of_assessment", "REF units of assessment.",
              ("id", "code", "name", "panel", "is_active")),
    Published("department", "department", "Departments.", ("id", "name", "code")),
)


# --------------------------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------------------------

def slug(subdomain: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", subdomain.lower()).strip("_")
    if not s or len(s) > 40:
        raise ValueError(f"Can't derive a schema name from subdomain {subdomain!r}")
    return s


def schemas(subdomain: str) -> tuple[str, str]:
    s = slug(subdomain)
    return f"tenant_{s}", f"tenant_{s}_full"


def reporting_roles(subdomain: str) -> tuple[str, str]:
    s = slug(subdomain)
    return f"{s}_reporting", f"{s}_reporting_full"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(value: str) -> str:
    # DDL can't take bind parameters; values here come from the catalogue, never from users.
    return "'" + value.replace("'", "''") + "'"


# --------------------------------------------------------------------------------------------
# Build (sync; async callers use `await conn.run_sync(rebuild)`)
# --------------------------------------------------------------------------------------------

def _scalar(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def view_owner(conn) -> str:
    """pgr_views when provisioned and usable; otherwise the current user (dev fallback, where the
    fixed tenant filter in each view is the lock and RLS applies as the table owner)."""
    usable = _scalar(conn,
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r) "
        "AND pg_has_role(current_user, :r, 'SET')", r=VIEW_OWNER)
    return VIEW_OWNER if usable else _scalar(conn, "SELECT current_user")


def drop_all(conn) -> int:
    """Drop every schema this module created (identified by its comment). Run before migrations."""
    names = [r[0] for r in conn.execute(text(
        "SELECT n.nspname FROM pg_namespace n "
        "WHERE obj_description(n.oid, 'pg_namespace') = :m"
    ), {"m": _MARKER})]
    for n in names:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {_q(n)} CASCADE"))
    return len(names)


def _columns(conn) -> dict[str, set[str]]:
    cols: dict[str, set[str]] = {}
    for t, c in conn.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"
    )):
        cols.setdefault(t, set()).add(c)
    return cols


def _select_list(obj: Published, have: set[str], full: bool) -> list[str]:
    items = [_q(c) for c in obj.columns if c in have]
    if full:
        items += [_q(c) for c in obj.personal if c in have]
    else:
        for alias, expr in obj.derived:
            # Only when every column the expression reads exists (older schemas during downgrades).
            if all(c in have for c in re.findall(r"[a-z_]+", expr) if c in obj.personal):
                items.append(f"{expr} AS {_q(alias)}")
    return items


def build_tenant(conn, tenant_id: uuid.UUID, subdomain: str, cols: dict[str, set[str]] | None = None,
                 owner: str | None = None) -> list[str]:
    """(Re)create both schemas for one institution. Returns the view names built."""
    cols = cols if cols is not None else _columns(conn)
    owner = owner or view_owner(conn)
    me = _scalar(conn, "SELECT current_user")
    std_role, full_role = reporting_roles(subdomain)
    roles = {r[0] for r in conn.execute(text(
        "SELECT rolname FROM pg_roles WHERE rolname IN (:a, :b)"), {"a": std_role, "b": full_role})}
    built: list[str] = []

    for schema, full in zip(schemas(subdomain), (False, True)):
        conn.execute(text(f"DROP SCHEMA IF EXISTS {_q(schema)} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {_q(schema)} AUTHORIZATION {_q(owner)}"))
        conn.execute(text(f"COMMENT ON SCHEMA {_q(schema)} IS '{_MARKER}'"))
        for obj in CATALOGUE:
            have = cols.get(obj.table)
            if not have or "tenant_id" not in have:
                logger.warning("tenant views: %s skipped, table %s not present", obj.name, obj.table)
                continue
            missing = [c for c in obj.columns if c not in have]
            if missing:
                logger.warning("tenant views: %s published without %s (not in this schema version)",
                               obj.name, missing)
            if owner != me:
                conn.execute(text(f"GRANT SELECT ON public.{_q(obj.table)} TO {_q(owner)}"))
            view = f"{_q(schema)}.{_q(obj.name)}"
            conn.execute(text(
                f"CREATE VIEW {view} WITH (security_barrier = true) AS "
                f"SELECT {', '.join(_select_list(obj, have, full))} FROM public.{_q(obj.table)} "
                f"WHERE tenant_id = '{uuid.UUID(str(tenant_id))}'::uuid"
            ))
            if owner != me:
                conn.execute(text(f"ALTER VIEW {view} OWNER TO {_q(owner)}"))
            note = obj.description + ("" if full else " (standard: personal data removed)")
            conn.execute(text(f"COMMENT ON VIEW {view} IS {_lit(note)}"))
            if not full:
                built.append(obj.name)

        grantees = [full_role] if full else [std_role, full_role]
        for role in grantees:
            if role in roles:
                conn.execute(text(f"GRANT USAGE ON SCHEMA {_q(schema)} TO {_q(role)}"))
                conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA {_q(schema)} TO {_q(role)}"))
    return built


def rebuild(conn, only: uuid.UUID | None = None) -> dict[str, int]:
    """Rebuild every active institution's schemas (or just one), and drop schemas of
    institutions that no longer exist or are deactivated. Returns {subdomain: views}."""
    cols = _columns(conn)
    if "subdomain" not in cols.get("tenant", set()):
        return {}   # a schema version from before multi-tenancy
    active = "WHERE deactivated_at IS NULL " if "deactivated_at" in cols["tenant"] else ""
    tenants = [(r[0], r[1]) for r in conn.execute(text(
        f"SELECT id, subdomain FROM tenant {active}ORDER BY subdomain"))]
    wanted = {n for _, sub in tenants for n in schemas(sub)}
    for (name,) in conn.execute(text(
        "SELECT n.nspname FROM pg_namespace n WHERE obj_description(n.oid, 'pg_namespace') = :m"
    ), {"m": _MARKER}).all():
        if name not in wanted:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {_q(name)} CASCADE"))
    owner = view_owner(conn)
    out = {}
    for tid, sub in tenants:
        if only is None or tid == only:
            out[sub] = len(build_tenant(conn, tid, sub, cols, owner))
    return out


async def rebuild_now(only: uuid.UUID | None = None) -> dict[str, int]:
    """Rebuild through the owner engine — for scripts that create or change institutions.
    A no-op off Postgres."""
    from app.core.database import engine

    if engine.dialect.name != "postgresql":
        return {}
    async with engine.begin() as conn:
        return await conn.run_sync(rebuild, only)
