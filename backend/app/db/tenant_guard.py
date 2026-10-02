"""T2 — the tenant-isolation guard: one place that says what "protected" means.

Every table is either tenant-owned (has ``tenant_id``) or on the explicit ``GLOBAL_TABLES``
list below. A tenant-owned table is protected only when, in Postgres, it has:

  * row-level security ENABLED and FORCED (so even the owner goes through the policies);
  * ``tenant_id`` NOT NULL;
  * exactly the two T1 policies (``tenant_ddl``) and no others — an extra permissive policy
    is OR'ed in and silently widens what a role can see:
      - ``tenant_isolation``         TO PUBLIC, rows of the acting tenant only (fail-closed);
      - ``tenant_isolation_system``  TO the table owner, the explicit bypass only.

The checks are used by the test suite (so a new table can't ship unprotected) and can be run
against any database by operators. A table that is genuinely global must be added to
``GLOBAL_TABLES`` with a reason — that list is the review point.
"""
from __future__ import annotations

from sqlalchemy import text

# Tables with no tenant column, on purpose. Each is safe because of the reason given.
GLOBAL_TABLES: dict[str, str] = {
    "tenant": "the tenant registry itself",
    "permission": "shared permission catalogue; read-only through the API",
    "role": "shared role catalogue; read-only through the API",
    "role_permission": "links the shared catalogues",
    "user_role": "reached only through users, which is tenant-scoped",
    "refresh_token": "looked up by token id, then tied to a tenant-scoped user",
    "password_reset_token": "looked up by token hash, then tied to a tenant-scoped user",
    "statutory_spec_version": "the published HESA specification, shared by every institution",
    "statutory_advisory": "HESA advisories that update the shared specification",
}

# Postgres bookkeeping, not application data.
_IGNORED = {"alembic_version"}


async def tenant_tables(conn) -> list[str]:
    rows = await conn.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'tenant_id' ORDER BY table_name"
    ))
    return [r[0] for r in rows]


async def check_database(conn) -> list[str]:
    """Every problem found, as readable lines. Empty means every table is protected."""
    problems: list[str] = []
    tenant = set(await tenant_tables(conn))

    all_tables = {r[0] for r in await conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ))}
    for table in sorted(all_tables - tenant - _IGNORED - set(GLOBAL_TABLES)):
        problems.append(f"{table}: no tenant_id and not listed in GLOBAL_TABLES")

    meta = {r[0]: r for r in await conn.execute(text(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner), "
        "       a.attnotnull "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
    ))}
    policies: dict[str, list] = {}
    for r in await conn.execute(text(
        "SELECT tablename, policyname, permissive, roles::text[], cmd, qual, with_check "
        "FROM pg_policies WHERE schemaname = 'public'"
    )):
        policies.setdefault(r[0], []).append(r)

    for table in sorted(tenant):
        m = meta.get(table)
        if m is None:
            continue  # a view, not a table
        _, rls, forced, owner, not_null = m
        if not rls:
            problems.append(f"{table}: row-level security is not enabled")
        if not forced:
            problems.append(f"{table}: row-level security is not forced")
        if not not_null:
            problems.append(f"{table}: tenant_id allows NULL")
        problems.extend(_check_policies(table, owner, policies.get(table, [])))
    return problems


def _check_policies(table: str, owner: str, rows: list) -> list[str]:
    out: list[str] = []
    by_name = {r[1]: r for r in rows}
    for extra in sorted(set(by_name) - {"tenant_isolation", "tenant_isolation_system"}):
        out.append(f"{table}: unexpected policy {extra!r} (extra policies widen access)")

    iso = by_name.get("tenant_isolation")
    if iso is None:
        out.append(f"{table}: missing policy tenant_isolation")
    else:
        _, _, permissive, roles, cmd, qual, check = iso
        if list(roles) != ["public"]:
            out.append(f"{table}: tenant_isolation applies to {roles}, expected PUBLIC")
        if cmd != "ALL":
            out.append(f"{table}: tenant_isolation covers {cmd}, expected ALL")
        for label, expr in (("USING", qual), ("WITH CHECK", check)):
            if not _is_fail_closed(expr):
                out.append(f"{table}: tenant_isolation {label} is not fail-closed: {expr}")

    system = by_name.get("tenant_isolation_system")
    if system is None:
        out.append(f"{table}: missing policy tenant_isolation_system")
    else:
        _, _, permissive, roles, cmd, qual, check = system
        if list(roles) != [owner]:
            out.append(f"{table}: tenant_isolation_system applies to {roles}, expected only {owner}")
        for label, expr in (("USING", qual), ("WITH CHECK", check)):
            if not expr or "app.bypass_tenant" not in expr or "tenant_id" in expr:
                out.append(f"{table}: tenant_isolation_system {label} is not the explicit bypass: {expr}")

    for r in rows:
        if r[2] != "PERMISSIVE":
            # A restrictive policy can only narrow access, but it isn't part of the layout.
            out.append(f"{table}: policy {r[1]!r} is {r[2]}, expected PERMISSIVE")
    return out


def _is_fail_closed(expr: str | None) -> bool:
    """tenant_id = <acting tenant>, and nothing that lets an unset tenant through."""
    if not expr:
        return False
    e = expr.lower()
    return (
        "tenant_id" in e
        and "app.current_tenant" in e
        and " or " not in e
        and "is null" not in e
        and "app.bypass_tenant" not in e
    )
