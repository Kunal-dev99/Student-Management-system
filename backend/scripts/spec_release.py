"""Release a HESA specification version to every subscribing institution, and see its impact.

    python -m scripts.spec_release versions HESA_STUDENT 2027/28
    python -m scripts.spec_release impact   HESA_STUDENT 2027/28 [--notify]
    python -m scripts.spec_release restore  <version-id>

The release itself is done in the app by the platform team (Statutory -> Import spec, or accept an
advisory); a specification version is shared, so it reaches every institution at once. This tool
covers the steps around it (docs/statutory/REGULATORY_RELEASE_PROCESS.md):

  versions  every version of the pack and year, the active one marked;
  impact    for every active institution, each return profile on that pack and year and what it
            still needs before sign-off (missing and unmapped required fields) - the same check
            as the sign-off screen. --notify also sends each institution's administrators an
            in-app notification that a new version is live;
  restore   make an earlier version active again (roll back a bad release). Nothing is deleted.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select

from app.core.database import SessionFactory
from app.core.tenant_context import system_scope, tenant_scope
from app.db import registry  # noqa: F401  (every model)
from app.modules.exports import spec_release


async def cmd_versions(pack: str, year: str) -> None:
    async with SessionFactory() as s:
        versions = await spec_release.list_versions(s, pack, year)
    if not versions:
        print(f"No released versions of {pack} {year} (the shipped baseline is in use).")
        return
    print(f"{'VERSION':8} {'STATUS':11} {'FIELDS':6} {'RULES':5}  ID")
    for v in versions:
        o = spec_release.version_out(v)
        print(f"{o['version']:<8} {o['status']:11} {o['fieldCount']:<6} {o['ruleCount']:<5}  {o['id']}")


async def _admins(s) -> list[uuid.UUID]:
    """Users of the acting institution who can configure it (admin.configure)."""
    from app.modules.identity.models import Permission, Role, User, role_permission, user_role

    rows = await s.execute(
        select(User.id).join(user_role, user_role.c.user_id == User.id)
        .join(Role, Role.id == user_role.c.role_id)
        .join(role_permission, role_permission.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permission.c.permission_id)
        .where(Permission.code == "admin.configure", User.is_active.is_(True)).distinct())
    return [r[0] for r in rows]


async def cmd_impact(pack: str, year: str, notify: bool) -> None:
    from app.modules.tenant.models import Tenant
    from app.modules.workflow.engine import WorkflowEngine

    async with SessionFactory() as s:
        active = await spec_release.list_versions(s, pack, year)
        tenants = (await s.execute(select(Tenant.id, Tenant.subdomain).where(
            Tenant.activated_at.is_not(None), Tenant.deactivated_at.is_(None)).order_by(Tenant.subdomain))).all()
    live = next((v for v in active if spec_release.version_out(v)["status"] == "active"), None)
    print(f"{pack} {year}: active version {live.version if live else 'baseline (none released)'}\n")
    affected = 0
    for tid, sub in tenants:
        async with tenant_scope(tid), SessionFactory() as s:
            profiles = await spec_release.impact(s, pack, year)
            for p in profiles:
                affected += 1
                state = "READY" if p["ready"] else "ACTION NEEDED"
                print(f"  {sub:12} {p['profile'][:40]:40} {state:13} "
                      f"missing={len(p['missing'])} unmapped-required={len(p['unmappedRequired'])}"
                      f"{' (signed off)' if p['signedOff'] else ''}")
                for f in (p["missing"] + p["unmappedRequired"])[:8]:
                    print(f"  {'':12}   - {f}")
            if notify and profiles:
                engine = WorkflowEngine(s)
                payload = {"pack": pack, "academicYear": year, "version": live.version if live else None,
                           "returnsNeedingAction": sum(not p["ready"] for p in profiles)}
                admins = await _admins(s)
                for uid in admins:
                    engine.notify(recipient_user_id=uid, template="spec.released", payload=payload)
                await s.commit()
                print(f"  {sub:12} notified {len(admins)} administrator(s)")
    if not affected:
        print("  No institution has a return profile on this pack and year.")


async def cmd_restore(version_id: str) -> None:
    async with system_scope(), SessionFactory() as s:
        v = await spec_release.restore(s, uuid.UUID(version_id), user_id=None)
        print(f"Version {v.version} of {v.pack_code} {v.academic_year} is active again.")


def main() -> None:
    p = argparse.ArgumentParser(description="Release a HESA specification version and see its impact.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("versions", "impact"):
        sp = sub.add_parser(name)
        sp.add_argument("pack", help="e.g. HESA_STUDENT")
        sp.add_argument("year", help="e.g. 2027/28")
        if name == "impact":
            sp.add_argument("--notify", action="store_true", help="tell each institution's administrators")
    sp = sub.add_parser("restore")
    sp.add_argument("version_id")
    a = p.parse_args()
    if a.cmd == "versions":
        asyncio.run(cmd_versions(a.pack, a.year))
    elif a.cmd == "impact":
        asyncio.run(cmd_impact(a.pack, a.year, a.notify))
    else:
        asyncio.run(cmd_restore(a.version_id))


if __name__ == "__main__":
    sys.exit(main())
