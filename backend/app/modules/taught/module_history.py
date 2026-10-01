"""Module enrolment dates and dated status (effective dating, Phase 3; feeds HESA ModuleInstance).

Each module enrolment carries the student's own start and end dates on the module (inclusive, as
HESA reports MODINSTSTARTDATE / MODINSTENDDATE) and a dated status history on the shared engine.

Rules:
- Defaults: from the later of the student's start and 1 August of the academic year, to 31 July
  (the HESA reporting year), clipped to the student's time on a programme that offers the module.
- Dates set explicitly must sit inside one period the student spent on a programme offering the
  module (its home programme or an elective offering). Students who predate programme history
  aren't checked.
- Withdrawing or interrupting ends the module on that date (HESA: the end date reflects the point
  the student withdrew or suspended).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from app.core.errors import WorkflowError
from app.modules.student_record.fact_history import FactHistoryService, ProgrammeHistoryService
from app.modules.student_record.models import Programme, Student
from app.modules.taught.constants import ModuleEnrolmentStatus
from app.modules.taught.models import (
    ModuleEnrolment,
    ModuleEnrolmentStatusHistory,
    ModuleOffering,
    TaughtModule,
)

# Statuses that end the student's time on the module on the effective date.
ENDING_STATUSES = {ModuleEnrolmentStatus.withdrawn, ModuleEnrolmentStatus.interrupted}


class ModuleStatusHistoryService(FactHistoryService):
    """``module_enrolment.status`` over time; the subject is the enrolment, not the student."""
    model = ModuleEnrolmentStatusHistory
    value_attr = "status"
    label = "module status"
    out_key = "status"
    subject_model = ModuleEnrolment
    subject_attr = "module_enrolment_id"
    subject_out_key = "moduleEnrolmentId"
    subject_label = "module enrolment"

    def initial_value(self, enrolment: ModuleEnrolment) -> ModuleEnrolmentStatus:
        return enrolment.status

    def cache_matches(self, enrolment: ModuleEnrolment, value) -> bool:
        return enrolment.status == value

    def apply_cache(self, enrolment: ModuleEnrolment, value) -> None:
        enrolment.status = value


def year_window(academic_year: str | None) -> tuple[date, date] | None:
    """'2026/27' -> (2026-08-01, 2027-07-31), the HESA reporting year (both inclusive)."""
    head = (academic_year or "").split("/", 1)[0].strip()
    if len(head) != 4 or not head.isdigit():
        return None
    y = int(head)
    return date(y, 8, 1), date(y + 1, 7, 31)


async def programmes_offering(session, module: TaughtModule) -> set[uuid.UUID]:
    """The module's home programme plus every programme it is offered on as an elective."""
    ids = {module.programme_id}
    rows = await session.execute(select(ModuleOffering.programme_id).where(ModuleOffering.module_id == module.id))
    ids.update(r[0] for r in rows)
    return ids


async def _programme_periods(session, student: Student, allowed: set[uuid.UUID]) -> list[tuple[date, date | None]]:
    """Inclusive (start, end) spans the student spent on programmes in ``allowed``."""
    rows = await ProgrammeHistoryService(session).live_rows(student.id)
    return [(r.valid_from, None if r.valid_to is None else date.fromordinal(r.valid_to.toordinal() - 1))
            for r in rows if r.programme_id in allowed]


async def default_dates(
    session, student: Student, module: TaughtModule, academic_year: str,
) -> tuple[date | None, date | None]:
    window = year_window(academic_year)
    if window is None:
        return student.start_date, None
    start, end = window
    if student.start_date is not None:
        start = max(start, student.start_date)
    if student.expected_end_date is not None:
        end = min(end, student.expected_end_date)
    # Clip to the student's time on a programme offering the module, where that overlaps.
    for p_start, p_end in await _programme_periods(session, student, await programmes_offering(session, module)):
        lo, hi = max(start, p_start), end if p_end is None else min(end, p_end)
        if lo <= hi:
            return lo, hi
    return start, (end if end >= start else None)


async def assert_dates_allowed(
    session, student: Student, module: TaughtModule, start: date | None, end: date | None,
) -> None:
    if start is not None and end is not None and end < start:
        raise WorkflowError("The module end date can't be before its start date")
    if start is None:
        return
    allowed = await programmes_offering(session, module)
    periods = await _programme_periods(session, student, allowed)
    if not await ProgrammeHistoryService(session).live_rows(student.id):
        return   # predates programme history: nothing to check against
    last = end or start
    if any(p_start <= start and (p_end is None or last <= p_end) for p_start, p_end in periods):
        return
    codes = sorted(
        p.code for p in (await session.execute(select(Programme).where(Programme.id.in_(allowed)))).scalars()
    )
    raise WorkflowError(
        f"The module dates ({start} to {end or 'open'}) must fall within the student's time on "
        f"{', '.join(codes) or 'a programme offering this module'}"
    )
