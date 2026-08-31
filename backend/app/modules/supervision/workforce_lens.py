"""W5 — Workforce lens.

Institution-wide supervisor capacity: who is over/at/under cap, who is on sabbatical or not
accepting new students, and how many assignment requests are pending. Bulk-loaded (a few queries
regardless of headcount) so it scales past a few hundred supervisors.

The population is the union of:
- everyone with a SupervisorProfile (W2 configured them explicitly),
- everyone with an active SupervisorRelationship (currently supervising),
- everyone named as the target of a pending assignment request.

Someone who has never supervised and has no profile stays off this list on purpose — the lens is
"the workforce we manage", not "every person in the institution".
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.person.models import Person
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship
from app.modules.supervision.w2_models import (
    AssignmentRequestState,
    SupervisorAvailability,
    SupervisorAssignmentRequest,
    SupervisorProfile,
)


ACTIVE_REQUEST_STATES = (
    AssignmentRequestState.recommended,
    AssignmentRequestState.requested,
    AssignmentRequestState.academic_review,
)


class WorkforceLensService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(self) -> dict:
        today = date.today()

        # Profiles keyed by person.
        profiles: dict[uuid.UUID, SupervisorProfile] = {
            p.person_id: p for p in (await self.session.execute(select(SupervisorProfile))).scalars().all()
        }

        # Active supervisor relationships — one row per (student, supervisor) currently in play.
        active_rels = (await self.session.execute(
            select(SupervisorRelationship).where(
                SupervisorRelationship.valid_to.is_(None),
                SupervisorRelationship.status == SupervisionStatus.assigned,
            )
        )).scalars().all()
        by_supervisor: dict[uuid.UUID, dict[str, int]] = {}
        for r in active_rels:
            b = by_supervisor.setdefault(r.supervisor_person_id, {"total": 0, "primary": 0, "co": 0})
            b["total"] += 1
            if r.role == SupervisorRole.primary:
                b["primary"] += 1
            else:
                b["co"] += 1

        # Pending assignment requests, targeting a supervisor.
        pending = (await self.session.execute(
            select(SupervisorAssignmentRequest).where(
                SupervisorAssignmentRequest.state.in_(ACTIVE_REQUEST_STATES),
            )
        )).scalars().all()
        pending_by: dict[uuid.UUID, int] = {}
        for r in pending:
            pending_by[r.proposed_supervisor_person_id] = pending_by.get(r.proposed_supervisor_person_id, 0) + 1

        # Population = union.
        person_ids: set[uuid.UUID] = set(profiles) | set(by_supervisor) | set(pending_by)

        # Institution default cap (used for people with no profile).
        from app.modules.settings.service import setting_value
        default_cap = int(await setting_value(self.session, "supervision.max_supervisees"))

        if not person_ids:
            return _empty(default_cap, len(pending))

        persons: dict[uuid.UUID, Person] = {
            p.id: p for p in (await self.session.execute(
                select(Person).where(Person.id.in_(list(person_ids)))
            )).scalars().all()
        }

        rows = []
        over_cap = 0
        on_sabbatical = 0
        unavailable = 0
        not_accepting = 0
        total_load = 0
        total_cap = 0

        for pid in person_ids:
            person = persons.get(pid)
            if person is None:
                continue
            profile = profiles.get(pid)
            caseload = by_supervisor.get(pid, {"total": 0, "primary": 0, "co": 0})
            cap = profile.max_students if profile else default_cap
            on_sab = bool(
                profile and profile.sabbatical_from and profile.sabbatical_to
                and profile.sabbatical_from <= today <= profile.sabbatical_to
            )
            availability = (profile.availability.value if profile else SupervisorAvailability.available.value)
            accepting = bool(profile.accepting_new) if profile else True
            is_unavailable = on_sab or availability == SupervisorAvailability.on_leave.value or not accepting

            over = caseload["total"] > cap
            headroom = cap - caseload["total"]
            if over:
                over_cap += 1
            if on_sab:
                on_sabbatical += 1
            if is_unavailable:
                unavailable += 1
            if not accepting:
                not_accepting += 1
            total_load += caseload["total"]
            total_cap += cap

            rows.append({
                "personId": str(pid),
                "personName": f"{person.given_name} {person.family_name}",
                "email": person.email,
                "hasProfile": profile is not None,
                "maxStudents": cap,
                "caseload": caseload["total"],
                "primary": caseload["primary"],
                "co": caseload["co"],
                "headroom": headroom,
                "overCapacity": over,
                "availability": availability,
                "acceptingNew": accepting,
                "onSabbatical": on_sab,
                "sabbaticalFrom": profile.sabbatical_from.isoformat() if profile and profile.sabbatical_from else None,
                "sabbaticalTo": profile.sabbatical_to.isoformat() if profile and profile.sabbatical_to else None,
                "pendingRequests": pending_by.get(pid, 0),
                "link": f"/supervision/{pid}",
            })

        # Sort: over-capacity first (worst breach), then by name.
        rows.sort(key=lambda r: (
            0 if r["overCapacity"] else 1,
            -(r["caseload"] - r["maxStudents"]) if r["overCapacity"] else 0,
            r["personName"],
        ))

        return {
            "totals": {
                "supervisors": len(rows),
                "overCapacity": over_cap,
                "onSabbatical": on_sabbatical,
                "notAcceptingNew": not_accepting,
                "unavailable": unavailable,
                "pendingRequests": len(pending),
                "totalActiveSupervisees": total_load,
                "totalCapacity": total_cap,
                "utilisationPct": round((total_load / total_cap) * 100, 1) if total_cap else 0.0,
                "defaultCap": default_cap,
            },
            "supervisors": rows,
        }


def _empty(default_cap: int, pending: int) -> dict:
    return {
        "totals": {
            "supervisors": 0, "overCapacity": 0, "onSabbatical": 0, "notAcceptingNew": 0,
            "unavailable": 0, "pendingRequests": pending, "totalActiveSupervisees": 0,
            "totalCapacity": 0, "utilisationPct": 0.0, "defaultCap": default_cap,
        },
        "supervisors": [],
    }
