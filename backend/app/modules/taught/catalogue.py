"""Module versions and yearly runs (effective dating, Phase 8 — Demo 2 item 1.3, the CMA rule).

A module is an identity (its code). What it teaches — title, credits, level, term — belongs to a
**version** in force over ``[valid_from, valid_to)``. Each year a version is taught is a **run**,
and every enrolment belongs to a run, so a student's credits always come from the version they
actually took.

Rules:
- versions of one module are contiguous and never overlap; the last one is open-ended;
- a version that students have enrolled on is never edited — a change is a new version from a date,
  which closes the old one; students already on the old version stay on it (CMA);
- ``taught_module`` caches the version in force today (refreshed daily, like the student facts);
- a run uses the version in force at the start of its academic year.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.student_record import fact_history
from app.modules.taught.models import ModuleEnrolment, ModuleRun, ModuleVersion, TaughtModule
from app.modules.taught.module_history import year_window

VERSIONED_FIELDS = ("title", "credits", "level", "term", "fte_pct")

# Credits in a full-time year when the home programme doesn't say (UK taught master's: 180).
DEFAULT_FULL_TIME_CREDITS = 180


def effective_fte(version, full_time_credits: int | None, *, exact: bool = False) -> Decimal | None:
    """Phase 8c — a module's FTE % (share of a full-time year): the version's own value if set,
    else credits ÷ the programme's full-time credits. None when neither is known. ``exact`` skips
    rounding to 2 places, for totals (4 × 16.67 would otherwise add up to 66.68)."""
    if version is None:
        return None
    if version.fte_pct is not None:
        return Decimal(version.fte_pct)
    if not version.credits:
        return None
    total = full_time_credits or DEFAULT_FULL_TIME_CREDITS
    value = Decimal(version.credits) * 100 / Decimal(total)
    return value if exact else value.quantize(Decimal("0.01"))


def academic_year_start(on: date | None = None) -> date:
    """1 August of the academic year containing ``on`` (default today)."""
    on = on or fact_history.today()
    return date(on.year if on.month >= 8 else on.year - 1, 8, 1)


def _covers(v: ModuleVersion, on: date) -> bool:
    return v.valid_from <= on and (v.valid_to is None or v.valid_to > on)


def label(v: ModuleVersion | None) -> str | None:
    return f"v{v.version_no}" if v is not None else None


class ModuleCatalogueService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- reads ----------------

    async def versions(self, module_id: uuid.UUID) -> list[ModuleVersion]:
        return list((await self.session.execute(
            select(ModuleVersion).where(ModuleVersion.module_id == module_id)
            .order_by(ModuleVersion.valid_from)
        )).scalars().all())

    async def version_at(self, module_id: uuid.UUID, on: date) -> ModuleVersion | None:
        """The version in force on ``on``; before the first version, the first one."""
        vs = await self.versions(module_id)
        return next((v for v in vs if _covers(v, on)), vs[0] if vs and on < vs[0].valid_from else
                    (vs[-1] if vs else None))

    async def full_time_credits(self, module: TaughtModule) -> int | None:
        """Credits in a full-time year for this module's home programme (for derived FTE)."""
        from app.modules.student_record.models import Programme

        p = await self.session.get(Programme, module.programme_id) if module.programme_id else None
        return p.taught_total_credits if p else None

    async def has_enrolments(self, version_id: uuid.UUID) -> bool:
        n = (await self.session.execute(
            select(func.count(ModuleEnrolment.id))
            .join(ModuleRun, ModuleRun.id == ModuleEnrolment.module_run_id)
            .where(ModuleRun.module_version_id == version_id)
        )).scalar()
        return bool(n)

    async def version_for_enrolment(self, e: ModuleEnrolment) -> ModuleVersion | None:
        if e.module_run_id is None:
            return None
        run = await self.session.get(ModuleRun, e.module_run_id)
        return await self.session.get(ModuleVersion, run.module_version_id) if run else None

    async def runs(self, module_id: uuid.UUID) -> list[tuple[ModuleRun, ModuleVersion, int]]:
        rows = (await self.session.execute(
            select(ModuleRun, ModuleVersion, func.count(ModuleEnrolment.id))
            .join(ModuleVersion, ModuleVersion.id == ModuleRun.module_version_id)
            .outerjoin(ModuleEnrolment, ModuleEnrolment.module_run_id == ModuleRun.id)
            .where(ModuleVersion.module_id == module_id)
            .group_by(ModuleRun.id, ModuleVersion.id)
            .order_by(ModuleRun.academic_year)
        )).all()
        return [(r, v, n) for r, v, n in rows]

    # ---------------- writes (callers commit) ----------------

    async def initialise(self, module: TaughtModule, *, valid_from: date | None = None,
                         user_id: uuid.UUID | None = None) -> ModuleVersion:
        """Version 1 from the module's current values (no-op if it has versions)."""
        existing = await self.versions(module.id)
        if existing:
            return existing[0]
        v = ModuleVersion(
            module_id=module.id, version_no=1, title=module.title, credits=module.credits or 0,
            level=module.level or 7, term=module.term, fte_pct=getattr(module, "fte_pct", None),
            valid_from=valid_from or academic_year_start(), valid_to=None,
            change_note="First version", created_by_user_id=user_id,
        )
        if getattr(module, "tenant_id", None) is not None:
            v.tenant_id = module.tenant_id
        self.session.add(v)
        await self.session.flush()
        return v

    async def run_for(self, module: TaughtModule, academic_year: str) -> ModuleRun:
        """The run of ``module`` in ``academic_year`` — the version in force at the year's start."""
        win = year_window(academic_year)
        on = win[0] if win else fact_history.today()
        version = await self.version_at(module.id, on) or await self.initialise(module)
        run = (await self.session.execute(
            select(ModuleRun).where(ModuleRun.module_version_id == version.id,
                                    ModuleRun.academic_year == academic_year)
        )).scalar_one_or_none()
        if run is None:
            run = ModuleRun(module_version_id=version.id, academic_year=academic_year,
                            start_date=win[0] if win else None, end_date=win[1] if win else None)
            if getattr(module, "tenant_id", None) is not None:
                run.tenant_id = module.tenant_id
            self.session.add(run)
            await self.session.flush()
        return run

    async def edit_current(self, module: TaughtModule, changes: dict) -> ModuleVersion | None:
        """Edit the version in force today — only while no student is enrolled on it."""
        changes = {k: v for k, v in changes.items() if k in VERSIONED_FIELDS}
        if not changes:
            return None
        current = await self.version_at(module.id, fact_history.today()) or await self.initialise(module)
        if await self.has_enrolments(current.id):
            raise ConflictError(
                f"Students are enrolled on {module.code} {label(current)}, so what it teaches can't be "
                "changed (CMA). Create a new version from the date the change applies; students "
                "already enrolled stay on their version."
            )
        for k, v in changes.items():
            setattr(current, k, v)
        await self.refresh_cache(module)
        return current

    async def new_version(self, module: TaughtModule, *, effective_from: date, changes: dict,
                          note: str | None, user_id: uuid.UUID | None) -> ModuleVersion:
        """A new version from ``effective_from``; the version it replaces ends then."""
        changes = {k: v for k, v in changes.items() if k in VERSIONED_FIELDS and v is not None}
        if not changes:
            raise WorkflowError("A new version needs at least one change (title, credits, level, term or FTE)")
        if not (note or "").strip():
            raise WorkflowError("Say what changed and why — it is shown against the version")
        vs = await self.versions(module.id) or [await self.initialise(module)]
        last = vs[-1]
        if last.valid_to is not None:
            raise WorkflowError(f"{module.code} is retired; it has no open version to replace")
        if effective_from <= last.valid_from:
            raise WorkflowError(
                f"The new version must start after the current one ({label(last)} from {last.valid_from})"
            )
        last.valid_to = effective_from
        values = {k: getattr(last, k) for k in VERSIONED_FIELDS} | changes
        v = ModuleVersion(module_id=module.id, version_no=last.version_no + 1, **values,
                          valid_from=effective_from, valid_to=None, change_note=note.strip(),
                          created_by_user_id=user_id)
        if getattr(module, "tenant_id", None) is not None:
            v.tenant_id = module.tenant_id
        self.session.add(v)
        await self.session.flush()
        await self.refresh_cache(module)
        return v

    async def refresh_cache(self, module: TaughtModule) -> bool:
        """Copy the version in force today onto the module row. True if anything changed."""
        v = await self.version_at(module.id, fact_history.today())
        if v is None:
            return False
        changed = False
        for k in VERSIONED_FIELDS:
            if getattr(module, k) != getattr(v, k):
                setattr(module, k, getattr(v, k))
                changed = True
        return changed

    async def refresh_due(self) -> int:
        """Daily: bring every module's cached values in line with today's version."""
        n = 0
        for m in (await self.session.execute(select(TaughtModule))).scalars().all():
            n += int(await self.refresh_cache(m))
        if n:
            await self.session.flush()
        return n

    # ---------------- output ----------------

    @staticmethod
    def version_out(v: ModuleVersion, *, enrolments: int | None = None,
                    full_time_credits: int | None = None) -> dict:
        fte = effective_fte(v, full_time_credits)
        return {
            "id": str(v.id), "moduleId": str(v.module_id), "versionNo": v.version_no,
            "label": label(v), "title": v.title, "credits": v.credits, "level": v.level, "term": v.term,
            # Phase 8c — module FTE %: set on the version, or derived from credits.
            "ftePct": float(fte) if fte is not None else None,
            "fteDerived": v.fte_pct is None and fte is not None,
            "validFrom": v.valid_from.isoformat(),
            "validTo": v.valid_to.isoformat() if v.valid_to else None,
            "changeNote": v.change_note, "enrolments": enrolments,
            # A version with students on it is locked (CMA).
            "locked": bool(enrolments),
        }

    async def catalogue(self, module_id: uuid.UUID) -> dict:
        module = await self.session.get(TaughtModule, module_id)
        if module is None:
            raise NotFoundError("Module not found")
        runs = await self.runs(module_id)
        counts: dict[uuid.UUID, int] = {}
        for _, v, n in runs:
            counts[v.id] = counts.get(v.id, 0) + n
        today = fact_history.today()
        full_time = await self.full_time_credits(module)
        return {
            "moduleId": str(module.id), "code": module.code,
            "versions": [self.version_out(v, enrolments=counts.get(v.id, 0), full_time_credits=full_time)
                         | {"current": _covers(v, today)}
                         for v in await self.versions(module_id)],
            "runs": [{"id": str(r.id), "academicYear": r.academic_year, "version": label(v),
                      "versionId": str(v.id),
                      "startDate": r.start_date.isoformat() if r.start_date else None,
                      "endDate": r.end_date.isoformat() if r.end_date else None, "enrolments": n}
                     for r, v, n in runs],
        }
