"""Retrospective changes against signed-off returns (effective dating, Phase 5).

A change is *retrospective* for a return when its period overlaps the return's reporting year
**and** it was recorded after the return was signed off:

    retrospective = valid_from < window_end
                and (valid_to is None or valid_to > window_start)
                and recorded_at > profile.signed_off_at

Two uses:

- **before** a change is made, ``warnings_for`` says which signed-off returns it would reach, so
  the approver sees "this may need resubmitting" while they can still decide;
- **after**, ``changes_since_signoff`` lists every student whose history moved inside a signed-off
  return's year, so Registry can decide whether to resubmit.

Backfilled rows are ignored: they were rebuilt from older data, not changed after sign-off.
Funding and supervision keep no recorded-at of their own, so their ``updated_at`` stands in.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.exports.models import ReportProfile
from app.modules.funding.models import FundingArrangement
from app.modules.person.models import Person
from app.modules.student_record.models import (
    Programme,
    Student,
    StudentCustomField,
    StudentCustomValue,
    StudentCustomValueHistory,
    StudentFeeStatusHistory,
    StudentIntensityHistory,
    StudentLocationHistory,
    StudentProgrammeHistory,
    StudentStatusHistory,
    StudentUoaHistory,
    PersonUoaHistory,
    UnitOfAssessment,
)
from app.modules.supervision.models import SupervisorRelationship
from app.modules.taught.models import ModuleEnrolment, ModuleEnrolmentStatusHistory, TaughtModule
from app.modules.taught.module_history import year_window


@dataclass(frozen=True)
class SignedReturn:
    profile_id: uuid.UUID
    code: str
    name: str
    academic_year: str
    window_start: date          # inclusive
    window_end: date            # exclusive
    signed_off_at: datetime

    def overlaps(self, valid_from: date, valid_to: date | None) -> bool:
        return valid_from < self.window_end and (valid_to is None or valid_to > self.window_start)

    def out(self) -> dict:
        return {
            "profileId": str(self.profile_id), "code": self.code, "name": self.name,
            "academicYear": self.academic_year,
            "signedOffAt": self.signed_off_at.isoformat(),
        }


def _signed(p: ReportProfile) -> SignedReturn | None:
    win = year_window(p.academic_year)
    if win is None or p.signed_off_at is None:
        return None
    return SignedReturn(p.id, p.code, p.name, p.academic_year, win[0], win[1] + timedelta(days=1),
                        p.signed_off_at)


async def signed_off_returns(session: AsyncSession) -> list[SignedReturn]:
    rows = (await session.execute(
        select(ReportProfile).where(ReportProfile.signed_off_at.is_not(None))
        .order_by(ReportProfile.academic_year, ReportProfile.code)
    )).scalars().all()
    return [s for s in (_signed(p) for p in rows) if s is not None]


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC so comparisons work in tests too."""
    if dt is not None and dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def affected(returns: list[SignedReturn], valid_from: date, valid_to: date | None,
             recorded_at: datetime | None) -> list[SignedReturn]:
    """The signed-off returns a recorded period reaches after their sign-off."""
    rec = _aware(recorded_at)
    return [r for r in returns
            if r.overlaps(valid_from, valid_to) and (rec is None or rec > _aware(r.signed_off_at))]


def _warning(r: SignedReturn, start: date) -> dict:
    signed = _aware(r.signed_off_at).date()
    return {
        **r.out(),
        "message": (
            f"This dates back to {start.strftime('%d %b %Y')}; the {r.name} {r.academic_year} return, "
            f"signed off on {signed.strftime('%d %b %Y')}, covers this period and may need resubmitting."
        ),
    }


async def warnings_for(
    session: AsyncSession, student: Student | None, start: date, end: date | None = None,
    *, returns: list[SignedReturn] | None = None,
) -> list[dict]:
    """Warnings for a change about to be recorded now, in force from ``start`` (to ``end``,
    exclusive, if bounded). A return only counts if the student was registered by its year end."""
    if returns is None:
        returns = await signed_off_returns(session)
    hits = []
    for r in affected(returns, start, end, None):   # recorded now = after every sign-off
        if student is not None and student.start_date is not None and student.start_date >= r.window_end:
            continue
        hits.append(_warning(r, start))
    return hits


# --------------------------------------------------------------------------------------
# After the fact: what moved inside a signed-off return's year
# --------------------------------------------------------------------------------------

def _overlap_clause(model, r: SignedReturn):
    return and_(model.valid_from < r.window_end,
                or_(model.valid_to.is_(None), model.valid_to > r.window_start))


def _val(v):
    return v.value if hasattr(v, "value") else v


async def changes_since_signoff(session: AsyncSession, profile_id: uuid.UUID) -> dict:
    p = await session.get(ReportProfile, profile_id)
    if p is None:
        raise NotFoundError("Report profile not found")
    r = _signed(p)
    base = {"profileId": str(p.id), "code": p.code, "name": p.name, "academicYear": p.academic_year,
            "signedOffAt": p.signed_off_at.isoformat() if p.signed_off_at else None}
    if r is None:
        return {**base, "signedOff": False, "students": [], "changeCount": 0}

    changes: list[dict] = []
    programme_names = {pid: name for pid, name in (await session.execute(
        select(Programme.id, Programme.name))).all()}
    uoa_codes = {u.id: u.code for u in (await session.execute(select(UnitOfAssessment))).scalars().all()}

    def add(student_id, fact, value, row, recorded_at, recorded_by=None):
        changes.append({
            "studentId": student_id, "fact": fact, "value": value,
            "validFrom": row.valid_from.isoformat(),
            "validTo": row.valid_to.isoformat() if row.valid_to else None,
            "origin": getattr(row, "origin", None), "reason": getattr(row, "reason", None),
            "recordedAt": _aware(recorded_at).isoformat() if recorded_at else None,
            "recordedByUserId": str(recorded_by) if recorded_by else None,
            "superseded": getattr(row, "superseded_by", None) is not None,
        })

    for model, fact, fmt in (
        (StudentStatusHistory, "status", lambda row: _val(row.status)),
        (StudentProgrammeHistory, "programme", lambda row: programme_names.get(row.programme_id)),
        (StudentIntensityHistory, "intensity", lambda row: f"{row.intensity_pct}%"),
        (StudentFeeStatusHistory, "fee_status", lambda row: row.fee_status),
        (StudentLocationHistory, "location", lambda row: row.study_location),
        (StudentUoaHistory, "uoa", lambda row: uoa_codes.get(row.uoa_id)),
    ):
        rows = (await session.execute(
            select(model).where(_overlap_clause(model, r), model.recorded_at > r.signed_off_at,
                                model.origin != "backfill", model.closure.is_(False))
        )).scalars().all()
        for row in rows:
            add(row.student_id, fact, fmt(row), row, row.recorded_at, row.recorded_by_user_id)

    h = ModuleEnrolmentStatusHistory
    rows = (await session.execute(
        select(h, ModuleEnrolment.student_id, TaughtModule.code)
        .join(ModuleEnrolment, ModuleEnrolment.id == h.module_enrolment_id)
        .join(TaughtModule, TaughtModule.id == ModuleEnrolment.module_id)
        .where(_overlap_clause(h, r), h.recorded_at > r.signed_off_at, h.origin != "backfill",
               h.closure.is_(False))
    )).all()
    for row, sid, code in rows:
        add(sid, "module", f"{code}: {_val(row.status)}", row, row.recorded_at, row.recorded_by_user_id)

    c = StudentCustomValueHistory
    rows = (await session.execute(
        select(c, StudentCustomValue.student_id, StudentCustomField.label)
        .join(StudentCustomValue, StudentCustomValue.id == c.custom_value_id)
        .join(StudentCustomField, StudentCustomField.id == StudentCustomValue.custom_field_id)
        .where(_overlap_clause(c, r), c.recorded_at > r.signed_off_at, c.origin != "backfill",
               c.closure.is_(False))
    )).all()
    for row, sid, label in rows:
        add(sid, "custom", f"{label}: {row.value}", row, row.recorded_at, row.recorded_by_user_id)

    rows = (await session.execute(
        select(FundingArrangement).where(_overlap_clause(FundingArrangement, r),
                                         FundingArrangement.updated_at > r.signed_off_at)
    )).scalars().all()
    for row in rows:
        add(row.student_id, "funding", _val(row.funding_type), row, row.updated_at)

    # Phase 9 — a supervisor's UOA changed after sign-off: it reaches every student they
    # supervised while the new UOA applied (Alistair's "UOA changed at the last minute").
    pu = PersonUoaHistory
    rel = SupervisorRelationship
    for row in (await session.execute(
        select(pu).where(_overlap_clause(pu, r), pu.recorded_at > r.signed_off_at,
                         pu.origin != "backfill", pu.closure.is_(False))
    )).scalars().all():
        for sup in (await session.execute(
            select(rel).where(rel.supervisor_person_id == row.person_id,
                              rel.valid_from < (row.valid_to or r.window_end),
                              or_(rel.valid_to.is_(None), rel.valid_to > row.valid_from))
        )).scalars().all():
            add(sup.student_id, "supervisor_uoa", f"{_val(sup.role)} supervisor: {uoa_codes.get(row.uoa_id)}",
                row, row.recorded_at, row.recorded_by_user_id)

    rows = (await session.execute(
        select(rel, Person.given_name, Person.family_name)
        .join(Person, Person.id == rel.supervisor_person_id)
        .where(_overlap_clause(rel, r), rel.updated_at > r.signed_off_at)
    )).all()
    for row, given, family in rows:
        add(row.student_id, "supervision", f"{_val(row.role)}: {given} {family}".strip(), row, row.updated_at)

    # Group by student, newest change first.
    ids = {c["studentId"] for c in changes}
    who = {}
    if ids:
        for sid, ref, given, family in (await session.execute(
            select(Student.id, Student.student_ref, Person.given_name, Person.family_name)
            .join(Person, Person.id == Student.person_id).where(Student.id.in_(ids))
        )).all():
            who[sid] = (ref, f"{given or ''} {family or ''}".strip())
    students: dict[uuid.UUID, dict] = {}
    for c in sorted(changes, key=lambda c: c["recordedAt"] or "", reverse=True):
        sid = c.pop("studentId")
        ref, name = who.get(sid, (None, None))
        entry = students.setdefault(sid, {"studentId": str(sid), "studentRef": ref, "name": name,
                                          "changes": []})
        entry["changes"].append(c)
    return {**base, "signedOff": True, "changeCount": len(changes),
            "students": sorted(students.values(), key=lambda s: s["studentRef"] or "")}
