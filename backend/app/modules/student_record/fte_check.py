"""Student FTE vs module FTE (Demo 2 item 1.5).

HESA expects a student's FTE (study intensity) in a year not to exceed the sum of the FTE of the
modules they take that year. How strictly that is enforced is an institution setting:

  statutory.fte_check            off | warn (default) | stop
  statutory.fte_check_tolerance  percentage points the student may exceed the module total by
  statutory.fte_check_research   also check research students (default off: they rarely take modules)

It is checked in two places, from the same rule (``evaluate``):

  - the statutory return's validation, per record: a warning, or an error that blocks sign-off;
  - approving an intensity change: a warning in the result, or (stop) the approval is refused.

A student with no module FTE in the year is not checked: there is nothing to compare yet, and
an empty module list early in the year is normal. Withdrawn modules don't count.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MODES = ("off", "warn", "stop")


@dataclass(frozen=True)
class FteCheckPolicy:
    mode: str = "warn"
    tolerance: float = 0.0
    check_research: bool = False

    @property
    def severity(self) -> str | None:
        return {"warn": "warning", "stop": "error"}.get(self.mode)


async def policy(session: AsyncSession) -> FteCheckPolicy:
    from app.modules.settings.service import setting_value

    mode = await setting_value(session, "statutory.fte_check")
    return FteCheckPolicy(
        mode=mode if mode in MODES else "warn",
        tolerance=float(await setting_value(session, "statutory.fte_check_tolerance") or 0),
        check_research=bool(await setting_value(session, "statutory.fte_check_research")),
    )


def evaluate(student_fte: float | None, module_fte: float | None, p: FteCheckPolicy, *,
             is_research: bool) -> str | None:
    """The message when the check fails, else None (off, not applicable, or within limits)."""
    if p.mode == "off" or student_fte is None or module_fte is None:
        return None
    if is_research and not p.check_research:
        return None
    if float(student_fte) <= float(module_fte) + p.tolerance + 1e-9:
        return None
    tol = f" (tolerance {p.tolerance:g} points)" if p.tolerance else ""
    return (f"Student FTE {float(student_fte):g}% is more than the total FTE of their modules "
            f"{float(module_fte):g}%{tol}. HESA expects it not to exceed the module total.")


def academic_year_of(on: date) -> str:
    """'2026/27' for any date from 1 Aug 2026 to 31 Jul 2027."""
    y = on.year if on.month >= 8 else on.year - 1
    return f"{y}/{str(y + 1)[-2:]}"


def module_fte_total(modules: list[dict]) -> float | None:
    """Sum of ``ftePct`` over a return record's modules, leaving out withdrawn ones."""
    known = [m["ftePct"] for m in modules if m.get("ftePct") is not None and m.get("status") != "withdrawn"]
    return round(sum(known), 2) if known else None


async def module_fte_for_year(session: AsyncSession, student_id: uuid.UUID, academic_year: str) -> float | None:
    """The student's module FTE in ``academic_year``, derived the same way as the return: the
    version of the run they took (else the module), credits ÷ the home programme's full-time
    credits when the version has no FTE of its own. None when nothing is known."""
    from app.modules.student_record.models import Programme
    from app.modules.taught.catalogue import effective_fte
    from app.modules.taught.constants import ModuleEnrolmentStatus
    from app.modules.taught.models import ModuleEnrolment, ModuleRun, ModuleVersion, TaughtModule

    rows = (await session.execute(
        select(ModuleEnrolment, TaughtModule, ModuleVersion, Programme.taught_total_credits)
        .join(TaughtModule, TaughtModule.id == ModuleEnrolment.module_id)
        .outerjoin(ModuleRun, ModuleRun.id == ModuleEnrolment.module_run_id)
        .outerjoin(ModuleVersion, ModuleVersion.id == ModuleRun.module_version_id)
        .outerjoin(Programme, Programme.id == TaughtModule.programme_id)
        .where(ModuleEnrolment.student_id == student_id,
               ModuleEnrolment.academic_year == academic_year,
               ModuleEnrolment.status != ModuleEnrolmentStatus.withdrawn)
    )).all()
    ftes = [effective_fte(v if v is not None else m, credits) for _, m, v, credits in rows]
    known = [f for f in ftes if f is not None]
    return float(round(sum(known, Decimal(0)), 2)) if known else None


async def check_intensity(session: AsyncSession, student, new_pct: int, effective: date) -> tuple[str | None, str | None]:
    """(severity, message) for setting ``student`` to ``new_pct`` from ``effective``; (None, None)
    when it passes or isn't checked."""
    from app.modules.student_record.constants import ProgrammeType
    from app.modules.student_record.models import Programme

    p = await policy(session)
    if p.severity is None:
        return None, None
    year = academic_year_of(effective)
    module_fte = await module_fte_for_year(session, student.id, year)
    ptype = (await session.execute(
        select(Programme.programme_type).where(Programme.id == student.programme_id)
    )).scalar_one_or_none() if student.programme_id else None
    msg = evaluate(new_pct, module_fte, p, is_research=ptype is not ProgrammeType.taught)
    return (p.severity, f"{year}: {msg}") if msg else (None, None)
