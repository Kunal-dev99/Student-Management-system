"""Demo logins for statutory returns and custom attribute governance — two institutions.

DEMO ONLY, like ``seed_demo_logins``: known passwords, refuses to run with APP_ENV=production,
never part of ``app.db.seed``. Idempotent — re-running resets each account's roles and password,
so a demo can always be recovered to a known state.

Per institution it creates the cast a statutory / custom-attribute demo needs:

  requester  — PGR Administrator: raises custom-attribute requests, runs the return
  approver   — Institution Administrator: decides requests, maps fields, signs off
  approver 2 — Institution Administrator: the "someone else" for maker-checker steps
               (e.g. retiring an attribute another approver put under review)
  supervisor — Supervisor: shows that statutory is not visible to academic staff

Institutions: ICR (the ``default`` tenant) and Oxbridge University (``oxbridge``). Each login
belongs to exactly one institution, which is what the multi-tenancy demo relies on: an Oxbridge
login never sees ICR's students, returns or custom attributes, and vice versa. Oxbridge also gets
a HESA Student 2026/27 return created from the spec if it has none, so there is something to show.

    python -m scripts.seed_statutory_demo
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.core.database import SessionFactory
from app.core.security import hash_password
from app.core.tenant_context import system_scope, tenant_scope
from app.modules.identity.models import Role, User
from app.modules.person.models import Person

# subdomain -> (label, password, [(email, roles, (given, family), what it's for)])
INSTITUTIONS = {
    "default": ("Institute of Cancer Research", "ICRdemo2026!", [
        ("requester@icr.demo", ["PGR Administrator"], ("Riya", "Patel"), "Requests attributes, runs the return"),
        ("approver@icr.demo", ["Institution Administrator"], ("James", "Holt"), "Approves, maps, signs off"),
        ("approver2@icr.demo", ["Institution Administrator"], ("Sofia", "Marsh"), "Second approver (maker-checker)"),
        ("supervisor@icr.demo", ["Supervisor"], ("Owen", "Clarke"), "No statutory access"),
    ]),
    "oxbridge": ("Oxbridge University", "OXBdemo2026!", [
        ("requester@oxbridge.demo", ["PGR Administrator"], ("Hannah", "Reed"), "Requests attributes, runs the return"),
        ("approver@oxbridge.demo", ["Institution Administrator"], ("Daniel", "Ward"), "Approves, maps, signs off"),
        ("approver2@oxbridge.demo", ["Institution Administrator"], ("Grace", "Lin"), "Second approver (maker-checker)"),
        ("supervisor@oxbridge.demo", ["Supervisor"], ("Tom", "Barker"), "No statutory access"),
    ]),
}
DEMO_RETURN = ("HESA_STUDENT:2026/27", "2026/27")


async def _tenant_id(subdomain: str):
    async with system_scope(), SessionFactory() as s:
        tid = (await s.execute(text("SELECT id FROM tenant WHERE subdomain = :s AND deactivated_at IS NULL")
                               .bindparams(s=subdomain))).scalar_one_or_none()
    if tid is None:
        sys.exit(f"No active institution with subdomain '{subdomain}'.")
    return tid


async def _seed_institution(subdomain: str, password: str, accounts: list) -> list[str]:
    tid = await _tenant_id(subdomain)
    notes = []
    async with tenant_scope(tid), SessionFactory() as s:
        roles = {r.name: r for r in (await s.execute(select(Role))).scalars().all()}
        missing = {n for _e, rs, _p, _d in accounts for n in rs} - set(roles)
        if missing:
            sys.exit(f"Roles not seeded yet: {missing}. Run `python -m app.db.seed` first.")
        for email, role_names, (given, family), _desc in accounts:
            person = (await s.execute(select(Person).where(Person.email == email))).scalars().first()
            if person is None:
                person = Person(given_name=given, family_name=family, email=email)
                s.add(person)
                await s.flush()
            user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(email=email)
                s.add(user)
                await s.flush()
            user.password_hash = hash_password(password)
            user.is_active = True
            user.failed_login_count = 0
            user.locked_until = None
            user.person_id = person.id
            await s.refresh(user, ["roles"])
            user.roles = [roles[n] for n in role_names]
        await s.commit()

        # Something statutory to show in every demo institution.
        from app.modules.exports.models import ReportProfile
        from app.modules.exports.statutory import StatutoryEngine

        spec_key, year = DEMO_RETURN
        code = spec_key.split(":")[0]
        exists = (await s.execute(select(ReportProfile).where(
            ReportProfile.code == code, ReportProfile.academic_year == year))).scalars().first()
        if exists is None:
            await StatutoryEngine(s).from_spec(spec_key=spec_key, academic_year=year)
            notes.append(f"created {code} {year} return from the spec")
        students = (await s.execute(text("SELECT count(*) FROM student"))).scalar_one()
        notes.append(f"{students} students")
    return notes


async def main() -> None:
    from app.core.config import get_settings

    if get_settings().app_env == "production":
        raise SystemExit("seed_statutory_demo refuses to run with APP_ENV=production")
    print(f"{'INSTITUTION':30} {'EMAIL':28} {'PASSWORD':14} ROLE — USE")
    for subdomain, (label, password, accounts) in INSTITUTIONS.items():
        notes = await _seed_institution(subdomain, password, accounts)
        for email, role_names, _p, desc in accounts:
            print(f"{label:30} {email:28} {password:14} {', '.join(role_names)} — {desc}")
        print(f"{'':30} ({'; '.join(notes)})")


if __name__ == "__main__":
    asyncio.run(main())
