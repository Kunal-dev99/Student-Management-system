"""A student's dated history in one place, and the record as it stood on a date (Phase 5).

``history`` merges every effective-dated fact — status, programme, study intensity, module status,
funding and supervision — into one list of periods, each with who recorded it, when, and whether a
signed-off return already covered it ("retrospective"). ``as_of`` answers "what was true on this
day?" from the same periods. Both read only; the history services stay the only writers.

Dates out: ``validFrom`` inclusive, ``validTo`` exclusive (None = still in force), as everywhere
else in the history API. The screen shows the inclusive end.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.identity.models import User
from app.modules.person.models import Person
from app.modules.student_record.fact_history import (
    CustomValueHistoryService,
    FeeStatusHistoryService,
    IntensityHistoryService,
    LocationHistoryService,
    ProgrammeHistoryService,
    StatusHistoryService,
    mode_for_intensity,
)
from app.modules.student_record.models import (
    Programme,
    Student,
    StudentCustomField,
    StudentCustomValue,
    StudentCustomValueHistory,
)
from app.modules.student_record.retrospective import affected, signed_off_returns
from app.modules.supervision.models import SupervisorRelationship
from app.modules.taught.models import ModuleEnrolment, ModuleEnrolmentStatusHistory, TaughtModule

FACTS = ("status", "programme", "intensity", "fee_status", "location", "module", "funding",
         "supervision", "custom")


def _val(v):
    return v.value if hasattr(v, "value") else v


def _covers(valid_from: date, valid_to: date | None, on: date) -> bool:
    return valid_from <= on and (valid_to is None or valid_to > on)


def _shown(rows: list, include_superseded: bool) -> list[tuple]:
    """(row, origin row) pairs to display from all of one fact's rows (Phase 7).

    A period that ended is superseded by a closed copy, so the live row may be a closure: it is
    shown with the recording details of the change that opened the period (who and when), not
    of the later change that closed it. "Include corrected rows" adds rows that were corrected
    or replaced the same day — never the open-ended versions that closures replaced."""
    by_id = {r.id: r for r in rows}
    pred_of = {r.superseded_by: r for r in rows if r.superseded_by is not None}

    def origin_of(r):
        seen = 0
        while getattr(r, "closure", False) and r.id in pred_of and seen < 50:
            r, seen = pred_of[r.id], seen + 1
        return r

    out = []
    for r in rows:
        if r.superseded_by is None:
            out.append((r, origin_of(r)))
        elif include_superseded and not getattr(by_id.get(r.superseded_by), "closure", False):
            out.append((r, origin_of(r)))
    return out


class StudentTimeline:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _student(self, student_id: uuid.UUID) -> Student:
        s = await self.session.get(Student, student_id)
        if s is None:
            raise NotFoundError("Student not found")
        return s

    async def _module_rows(self, student_id: uuid.UUID, include_superseded: bool):
        h = ModuleEnrolmentStatusHistory
        q = (select(h, ModuleEnrolment, TaughtModule)
             .join(ModuleEnrolment, ModuleEnrolment.id == h.module_enrolment_id)
             .join(TaughtModule, TaughtModule.id == ModuleEnrolment.module_id)
             .where(ModuleEnrolment.student_id == student_id)
             .order_by(h.valid_from, h.recorded_at))
        if not include_superseded:
            q = q.where(h.superseded_by.is_(None))
        return (await self.session.execute(q)).all()

    async def _funding(self, student_id: uuid.UUID):
        return (await self.session.execute(
            select(FundingArrangement, FundingSource.name)
            .outerjoin(FundingSource, FundingSource.id == FundingArrangement.funding_source_id)
            .where(FundingArrangement.student_id == student_id)
            .order_by(FundingArrangement.valid_from)
        )).all()

    async def _supervision(self, student_id: uuid.UUID):
        rel = SupervisorRelationship
        return (await self.session.execute(
            select(rel, Person.given_name, Person.family_name)
            .join(Person, Person.id == rel.supervisor_person_id)
            .where(rel.student_id == student_id)
            .order_by(rel.valid_from)
        )).all()

    async def _custom_rows(self, student_id: uuid.UUID, include_superseded: bool):
        """Dated values of the student's custom attributes that keep history (Phase 6)."""
        h = StudentCustomValueHistory
        q = (select(h, StudentCustomField)
             .join(StudentCustomValue, StudentCustomValue.id == h.custom_value_id)
             .join(StudentCustomField, StudentCustomField.id == StudentCustomValue.custom_field_id)
             .where(StudentCustomValue.student_id == student_id, StudentCustomField.track_history.is_(True))
             .order_by(h.valid_from, h.recorded_at))
        if not include_superseded:
            q = q.where(h.superseded_by.is_(None))
        return (await self.session.execute(q)).all()

    # ---------------- history ----------------

    async def history(self, student_id: uuid.UUID, *, include_superseded: bool = False) -> dict:
        student = await self._student(student_id)
        returns = await signed_off_returns(self.session)
        programme_names = {pid: name for pid, name in (await self.session.execute(
            select(Programme.id, Programme.name))).all()}
        entries: list[dict] = []
        users: set[uuid.UUID] = set()

        def add(fact, label, value, valid_from, valid_to, *, recorded_at=None, recorded_by=None,
                origin=None, reason=None, superseded=False, row_id=None, detail=None):
            if recorded_by:
                users.add(recorded_by)
            hits = [] if origin == "backfill" else affected(returns, valid_from, valid_to, recorded_at)
            entries.append({
                "id": str(row_id) if row_id else None, "fact": fact, "label": label, "value": value,
                "validFrom": valid_from.isoformat(),
                "validTo": valid_to.isoformat() if valid_to else None,
                "origin": origin, "reason": reason,
                "recordedAt": recorded_at.isoformat() if recorded_at else None,
                "recordedByUserId": str(recorded_by) if recorded_by else None,
                "superseded": superseded,
                "retrospective": [r.out() for r in hits],
                "detail": detail or {},
            })

        for svc, fact, fmt in (
            (StatusHistoryService, "status", lambda r: (_val(r.status), _val(r.status))),
            (ProgrammeHistoryService, "programme",
             lambda r: (programme_names.get(r.programme_id) or "—",
                        str(r.programme_id) if r.programme_id else None)),
            (IntensityHistoryService, "intensity",
             lambda r: (f"{r.intensity_pct}% ({mode_for_intensity(r.intensity_pct).value.replace('_', ' ')})",
                        r.intensity_pct)),
            (FeeStatusHistoryService, "fee_status", lambda r: (r.fee_status, r.fee_status)),
            (LocationHistoryService, "location", lambda r: (r.study_location, r.study_location)),
        ):
            for r, o in _shown(await svc(self.session).all_rows(student_id), include_superseded):
                label, value = fmt(r)
                add(fact, label, value, r.valid_from, r.valid_to, recorded_at=o.recorded_at,
                    recorded_by=o.recorded_by_user_id, origin=o.origin, reason=o.reason,
                    superseded=r.superseded_by is not None, row_id=r.id)

        module_rows = await self._module_rows(student_id, True)
        module_ctx = {r.id: (enr, mod) for r, enr, mod in module_rows}
        for r, o in _shown([r for r, _, _ in module_rows], include_superseded):
            enr, mod = module_ctx[r.id]
            add("module", f"{mod.code} {mod.title}: {_val(r.status)}", _val(r.status), r.valid_from, r.valid_to,
                recorded_at=o.recorded_at, recorded_by=o.recorded_by_user_id, origin=o.origin,
                reason=o.reason, superseded=r.superseded_by is not None, row_id=r.id,
                detail={"moduleEnrolmentId": str(enr.id), "moduleCode": mod.code,
                        "academicYear": enr.academic_year})

        custom_rows = await self._custom_rows(student_id, True)
        custom_ctx = {r.id: f for r, f in custom_rows}
        for r, o in _shown([r for r, _ in custom_rows], include_superseded):
            f = custom_ctx[r.id]
            add("custom", f"{f.label}: {r.value}", r.value, r.valid_from, r.valid_to,
                recorded_at=o.recorded_at, recorded_by=o.recorded_by_user_id, origin=o.origin,
                reason=o.reason, superseded=r.superseded_by is not None, row_id=r.id,
                detail={"key": f.key, "label": f.label})

        for a, source in await self._funding(student_id):
            label = _val(a.funding_type).replace("_", " ") + (f" — {source}" if source else "")
            if a.contribution_pct is not None:
                label += f" ({a.contribution_pct}%)"
            add("funding", label, _val(a.funding_type), a.valid_from, a.valid_to,
                recorded_at=a.updated_at or a.created_at, row_id=a.id,
                detail={"source": source, "contributionPct": a.contribution_pct,
                        "status": _val(a.status)})

        for rel, given, family in await self._supervision(student_id):
            name = f"{given or ''} {family or ''}".strip()
            add("supervision", f"{_val(rel.role).replace('_', ' ')}: {name}", name, rel.valid_from, rel.valid_to,
                recorded_at=rel.updated_at or rel.created_at, reason=rel.end_reason, row_id=rel.id,
                detail={"role": _val(rel.role), "supervisorPersonId": str(rel.supervisor_person_id)})

        emails = {}
        if users:
            emails = {uid: email for uid, email in (await self.session.execute(
                select(User.id, User.email).where(User.id.in_(users)))).all()}
        for e in entries:
            uid = e["recordedByUserId"]
            e["recordedBy"] = emails.get(uuid.UUID(uid)) if uid else None

        order = {f: i for i, f in enumerate(FACTS)}
        entries.sort(key=lambda e: (e["validFrom"], order[e["fact"]], e["recordedAt"] or ""))
        return {
            "studentId": str(student.id),
            "startDate": student.start_date.isoformat() if student.start_date else None,
            "signedOffReturns": [r.out() for r in returns],
            "retrospectiveCount": sum(1 for e in entries if e["retrospective"]),
            "entries": entries,
        }

    # ---------------- as of a date ----------------

    async def as_of(self, student_id: uuid.UUID, on: date) -> dict:
        student = await self._student(student_id)
        status = await StatusHistoryService(self.session).value_at(student_id, on)
        prog = await ProgrammeHistoryService(self.session).value_at(student_id, on)
        inten = await IntensityHistoryService(self.session).value_at(student_id, on)
        fee = await FeeStatusHistoryService(self.session).value_at(student_id, on)
        loc = await LocationHistoryService(self.session).value_at(student_id, on)
        custom = [
            {"key": f.key, "label": f.label, "value": r.value}
            for r, f in await self._custom_rows(student_id, False) if _covers(r.valid_from, r.valid_to, on)
        ]
        programme_name = None
        if prog is not None and prog.programme_id is not None:
            p = await self.session.get(Programme, prog.programme_id)
            programme_name = p.name if p else None

        modules = [
            {"moduleEnrolmentId": str(enr.id), "code": mod.code, "title": mod.title,
             "academicYear": enr.academic_year, "status": _val(r.status)}
            for r, enr, mod in await self._module_rows(student_id, False)
            if _covers(r.valid_from, r.valid_to, on)
        ]
        funding = [
            {"id": str(a.id), "type": _val(a.funding_type), "source": source,
             "contributionPct": a.contribution_pct,
             "validFrom": a.valid_from.isoformat(), "validTo": a.valid_to.isoformat() if a.valid_to else None}
            for a, source in await self._funding(student_id) if _covers(a.valid_from, a.valid_to, on)
        ]
        supervisors = [
            {"id": str(rel.id), "role": _val(rel.role), "name": f"{given or ''} {family or ''}".strip(),
             "validFrom": rel.valid_from.isoformat(), "validTo": rel.valid_to.isoformat() if rel.valid_to else None}
            for rel, given, family in await self._supervision(student_id)
            if _covers(rel.valid_from, rel.valid_to, on)
        ]
        before_start = student.start_date is not None and on < student.start_date
        return {
            "studentId": str(student.id), "asOf": on.isoformat(), "beforeStart": before_start,
            "status": _val(status.status) if status else None,
            "programmeId": str(prog.programme_id) if prog and prog.programme_id else None,
            "programmeName": programme_name,
            "intensityPct": inten.intensity_pct if inten else None,
            "studyMode": mode_for_intensity(inten.intensity_pct).value if inten else None,
            "feeStatus": fee.fee_status if fee else None,
            "studyLocation": loc.study_location if loc else None,
            "custom": custom,
            "modules": modules, "funding": funding, "supervisors": supervisors,
        }
