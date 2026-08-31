"""ICR read models — cohort, transfer-viva pipeline, pathways, funding.

Every query below runs over the EXISTING tables (student, milestone,
milestone_definition, funding_arrangement, person). The ICR module adds views;
it owns no tables of its own and changes no core behaviour.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.icr.constants import (
    DATA_BARRIER_NAME,
    PATHWAYS,
    PROVISIONAL_MPHIL,
    TRANSFER_VIVA_NAME,
    UPGRADED_PHD,
)
from app.modules.person.models import Person
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.models import Programme, Student

LIVE = ("registered", "active", "on_leave", "suspended")


class IcrService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _programmes(self) -> dict[str, Programme]:
        rows = (await self.session.execute(
            select(Programme).where(Programme.code.in_(list(PATHWAYS)))
        )).scalars().all()
        return {p.code: p for p in rows}

    async def _students(self, codes: list[str] | None = None) -> list[tuple[Student, Person, Programme]]:
        progs = await self._programmes()
        wanted = [p.id for c, p in progs.items() if not codes or c in codes]
        if not wanted:
            return []
        rows = (await self.session.execute(
            select(Student, Person, Programme)
            .join(Person, Person.id == Student.person_id)
            .join(Programme, Programme.id == Student.programme_id)
            .where(Student.programme_id.in_(wanted))
            .order_by(Student.start_date)
        )).all()
        return [(s, p, pr) for s, p, pr in rows]

    async def _milestones_by_student(self, student_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[Milestone, MilestoneDefinition]]]:
        if not student_ids:
            return {}
        rows = (await self.session.execute(
            select(Milestone, MilestoneDefinition)
            .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
            .where(Milestone.student_id.in_(student_ids))
        )).all()
        out: dict[uuid.UUID, list] = {}
        for m, d in rows:
            out.setdefault(m.student_id, []).append((m, d))
        for v in out.values():
            v.sort(key=lambda t: t[1].due_offset_days)
        return out

    @staticmethod
    def _months_in(student: Student) -> int | None:
        if student.start_date is None:
            return None
        return max(0, (date.today() - student.start_date).days // 30)

    @staticmethod
    def _registration(ms: list[tuple[Milestone, MilestoneDefinition]], clinical: bool,
                      persisted: str | None = None) -> str:
        """MPhil until the transfer viva is decided — the ICR model's core gate.

        ICR gap 1 — prefer the persisted ``student.registration_status`` when it has been set by
        progression.decide (the flip). Falling back to the milestone-derived view keeps the pre-
        gap-1 behaviour for records that have never had a transfer viva decided under the flip.
        """
        if persisted:
            return persisted
        if clinical:
            return "MD(Res)"
        for m, d in ms:
            if d.name == TRANSFER_VIVA_NAME:
                return UPGRADED_PHD if m.status.value == "decided" else PROVISIONAL_MPHIL
        return PROVISIONAL_MPHIL

    # ------------------------------------------------------------------ views

    async def overview(self) -> dict:
        students = await self._students()
        live = [(s, p, pr) for s, p, pr in students if s.status.value in LIVE]
        ms_by = await self._milestones_by_student([s.id for s, _, _ in live])

        pathways = []
        for code, meta in PATHWAYS.items():
            rows = [(s, p, pr) for s, p, pr in live if pr.code == code]
            upgraded = sum(
                1 for s, _, _ in rows
                if self._registration(ms_by.get(s.id, []), meta["clinical"], s.registration_status) == UPGRADED_PHD
            )
            pathways.append({
                "code": code, "label": meta["label"], "detail": meta["detail"],
                "durationMonths": meta["durationMonths"], "clinical": meta["clinical"],
                "students": len(rows),
                "upgraded": upgraded,
                "provisional": len(rows) - upgraded if not meta["clinical"] else 0,
            })

        # Transfer-viva pipeline buckets (non-clinical only — it is the PhD gate).
        awaiting, due_soon, overdue, done = 0, 0, 0, 0
        for s, _, pr in live:
            if PATHWAYS.get(pr.code, {}).get("clinical"):
                continue
            tv = next((m for m, d in ms_by.get(s.id, []) if d.name == TRANSFER_VIVA_NAME), None)
            if tv is None:
                continue
            if tv.status.value == "decided":
                done += 1
            elif tv.due_date and tv.due_date < date.today():
                overdue += 1
            elif tv.due_date and (tv.due_date - date.today()).days <= 90:
                due_soon += 1
            else:
                awaiting += 1

        # Approaching the hard submission limit.
        near_limit = 0
        for s, _, pr in live:
            months = self._months_in(s)
            limit = PATHWAYS.get(pr.code, {}).get("durationMonths", 48)
            if months is not None and months >= limit - 6:
                near_limit += 1

        funders = await self.funding()
        return {
            "cohort": len(live),
            "allTime": len(students),
            "pathways": pathways,
            "transferViva": {"awaiting": awaiting, "dueSoon": due_soon,
                             "overdue": overdue, "upgraded": done},
            "nearSubmissionLimit": near_limit,
            "funders": funders["funders"],
        }

    async def transfer_viva(self) -> dict:
        """The upgrade tracker: every non-clinical student against the 12-14 month gate."""
        students = await self._students(["ICR-PHD"])
        live = [(s, p, pr) for s, p, pr in students if s.status.value in LIVE]
        ms_by = await self._milestones_by_student([s.id for s, _, _ in live])
        rows = []
        for s, p, _ in live:
            tv = next(((m, d) for m, d in ms_by.get(s.id, []) if d.name == TRANSFER_VIVA_NAME), None)
            if tv is None:
                continue
            m, d = tv
            days = (m.due_date - date.today()).days if m.due_date else None
            state = ("upgraded" if m.status.value == "decided"
                     else "overdue" if days is not None and days < 0
                     else "due soon" if days is not None and days <= 90
                     else "scheduled")
            rows.append({
                "studentId": str(s.id), "studentRef": s.student_ref,
                "name": f"{p.given_name} {p.family_name}",
                "startDate": s.start_date.isoformat() if s.start_date else None,
                "monthsIn": self._months_in(s),
                "dueDate": m.due_date.isoformat() if m.due_date else None,
                "daysUntilDue": days,
                "milestoneStatus": m.status.value,
                "registration": self._registration(ms_by.get(s.id, []), False, s.registration_status),
                "state": state,
                "requiredDocuments": d.required_documents,
                "panel": d.review_panel,
            })
        order = {"overdue": 0, "due soon": 1, "scheduled": 2, "upgraded": 3}
        rows.sort(key=lambda r: (order.get(r["state"], 9), r["daysUntilDue"] if r["daysUntilDue"] is not None else 9999))
        return {"rows": rows, "checkpoint": TRANSFER_VIVA_NAME}

    async def pathways(self) -> dict:
        """Both tracks side by side, each student with their ICR stage."""
        students = await self._students()
        ms_by = await self._milestones_by_student([s.id for s, _, _ in students])
        out = []
        for s, p, pr in students:
            meta = PATHWAYS.get(pr.code, {})
            ms = ms_by.get(s.id, [])
            decided = sum(1 for m, _ in ms if m.status.value == "decided")
            barrier = next(((m, d) for m, d in ms if d.name == DATA_BARRIER_NAME), None)
            months = self._months_in(s)
            limit = meta.get("durationMonths", 48)
            out.append({
                "studentId": str(s.id), "studentRef": s.student_ref,
                "name": f"{p.given_name} {p.family_name}",
                "pathway": meta.get("label", pr.name), "clinical": meta.get("clinical", False),
                "status": s.status.value, "studyMode": s.study_mode.value,
                "startDate": s.start_date.isoformat() if s.start_date else None,
                "monthsIn": months,
                "limitMonths": limit,
                "monthsRemaining": (limit - months) if months is not None else None,
                "registration": self._registration(ms, meta.get("clinical", False), s.registration_status),
                "checkpointsPassed": decided,
                "checkpointsTotal": len(ms),
                "dataBarrier": (barrier[0].status.value if barrier else None),
            })
        return {"rows": out}

    async def funding(self) -> dict:
        """ICR funder pillars: who pays, for how many, at what committed stipend."""
        progs = await self._programmes()
        prog_ids = [p.id for p in progs.values()]
        if not prog_ids:
            return {"funders": [], "totalStudents": 0}
        rows = (await self.session.execute(
            select(
                FundingSource.name,
                FundingSource.funder_type,
                func.count(func.distinct(FundingArrangement.student_id)),
                func.sum(FundingArrangement.stipend_amount),
            )
            .join(FundingArrangement, FundingArrangement.funding_source_id == FundingSource.id)
            .join(Student, Student.id == FundingArrangement.student_id)
            .where(Student.programme_id.in_(prog_ids))
            .group_by(FundingSource.name, FundingSource.funder_type)
            .order_by(func.count(func.distinct(FundingArrangement.student_id)).desc())
        )).all()
        funders = [{
            "name": n, "funderType": t, "students": int(c or 0),
            "committedStipend": str(total) if total is not None else None,
        } for n, t, c, total in rows]
        return {"funders": funders, "totalStudents": sum(f["students"] for f in funders)}
