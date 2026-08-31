"""Create the demo login accounts — one per role, plus the variations worth showing.

DEMO ONLY. This is deliberately *not* part of `app.db.seed`, which runs on every deploy:
production must never acquire known-password accounts as a side effect of a release.

Idempotent — safe to re-run. Existing accounts have their role set and password reset to
the documented value, so a demo can always be recovered to a known state.

    python -m scripts.seed_demo_logins
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.core.database import SessionFactory
from app.core.security import hash_password
from app.modules.identity.models import Role, User
from app.modules.person.models import Person

# email, password, [roles], person hint (given, family) or None to leave unlinked
ACCOUNTS = [
    ("admin@example.com", "admin123",
     ["Institution Administrator", "PGR Administrator"], None,
     "Full access — every permission including admin.configure and ml.approve"),
    ("pgr.admin@example.com", "pgr123",
     ["PGR Administrator"], ("Amara", "Osei"),
     "The day-job administrator: cannot change institution settings or approve ML models"),
    ("rosa.grigsby@example.com", "super123",
     ["Supervisor"], ("Rosa", "Grigsby"),
     "Supervisor with a full caseload"),
    ("elena.ford@example.com", "super123",
     ["Supervisor"], ("Elena", "Ford"),
     "Supervisor with a small caseload"),
    ("exec@example.com", "exec123",
     ["Executive"], ("Helen", "Whitfield"),
     "Dashboards only — no access to individual student records"),
    ("marcus.bell@example.ac.uk", "student123",
     ["Student"], ("Marcus", "Bell"),
     "Student portal — sees only their own record"),
]


async def main() -> None:
    async with SessionFactory() as s:
        roles = {r.name: r for r in (await s.execute(select(Role))).scalars().all()}
        missing = {n for _e, _p, rs, _h, _d in ACCOUNTS for n in rs} - set(roles)
        if missing:
            sys.exit(f"Roles not seeded yet: {missing}. Run `python -m app.db.seed` first.")

        for email, pw, role_names, hint, _desc in ACCOUNTS:
            person = None
            if hint:
                given, family = hint
                person = (await s.execute(
                    select(Person).where(Person.given_name == given,
                                         Person.family_name == family)
                )).scalars().first()
                if person is None:                       # invent the person if absent
                    person = Person(given_name=given, family_name=family,
                                    email=email)
                    s.add(person)
                    await s.flush()

            user = (await s.execute(
                select(User).where(User.email == email)
            )).scalar_one_or_none()
            if user is None:
                user = User(email=email)
                s.add(user)
                await s.flush()
            user.password_hash = hash_password(pw)
            user.is_active = True
            user.failed_login_count = 0
            user.locked_until = None
            if person is not None:
                user.person_id = person.id
            await s.refresh(user, ["roles"])
            user.roles = [roles[n] for n in role_names]
        await s.commit()

        # Report the resulting state, including each supervisor's live caseload.
        print(f"{'EMAIL':30} {'PASSWORD':12} {'ROLE(S)':42} CASELOAD")
        for email, pw, role_names, _hint, _desc in ACCOUNTS:
            n = (await s.execute(text("""
                SELECT count(*) FROM supervisor_relationship sr
                JOIN users u ON u.person_id = sr.supervisor_person_id
                WHERE u.email = :e AND sr.valid_to IS NULL"""), {"e": email})).scalar_one()
            print(f"{email:30} {pw:12} {', '.join(role_names):42} {n or '-'}")


if __name__ == "__main__":
    asyncio.run(main())
