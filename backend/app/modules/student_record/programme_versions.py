"""Programme versions and cohort pinning (effective dating, Phase 8b — Demo 2 item 1.3, the CMA rule).

The CMA rule: a university can't change what it sold. A cohort that enrolled on a programme runs
on that version to completion; a new cohort can be advertised on a new version.

- A **version** holds what was promised, in force over ``[valid_from, valid_to)``: total credits,
  duration, grading policy and the module structure (which modules, core or optional).
- A student is **pinned** to the version in force on the day they started on the programme
  (enrolment or transfer). Their core modules and award rules come from that version.
- A version students are pinned to is **locked**: it may gain modules, but removing one, making a
  core module optional, or changing the rules needs a new version from a date.
- ``programme`` caches today's version's rules (refreshed daily), like the other dated facts.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.student_record import fact_history
from app.modules.student_record.models import (
    Programme,
    ProgrammeVersion,
    Student,
    StudentProgrammePin,
)

RULE_FIELDS = ("taught_total_credits", "duration_months", "grading_policy")


def _ay_start(d: date) -> date:
    return date(d.year if d.month >= 8 else d.year - 1, 8, 1)


def _covers(v: ProgrammeVersion, on: date) -> bool:
    return v.valid_from <= on and (v.valid_to is None or v.valid_to > on)


def label(v: ProgrammeVersion | None) -> str | None:
    return f"v{v.version_no}" if v is not None else None


class ProgrammeVersionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- reads ----------------

    async def versions(self, programme_id: uuid.UUID) -> list[ProgrammeVersion]:
        return list((await self.session.execute(
            select(ProgrammeVersion).where(ProgrammeVersion.programme_id == programme_id)
            .order_by(ProgrammeVersion.valid_from)
        )).scalars().all())

    async def version_at(self, programme_id: uuid.UUID, on: date) -> ProgrammeVersion | None:
        vs = await self.versions(programme_id)
        if not vs:
            return None
        hit = next((v for v in vs if _covers(v, on)), None)
        return hit or (vs[0] if on < vs[0].valid_from else vs[-1])

    async def pinned_count(self, version_id: uuid.UUID) -> int:
        return int((await self.session.execute(
            select(func.count(StudentProgrammePin.id))
            .where(StudentProgrammePin.programme_version_id == version_id)
        )).scalar() or 0)

    async def live_structure(self, programme_id: uuid.UUID) -> list[dict]:
        """The programme's modules as configured now: home modules (core or optional) plus
        electives offered from other programmes (optional)."""
        from app.modules.taught.models import ModuleOffering, TaughtModule

        out = [{"moduleId": str(m.id), "code": m.code, "isCore": bool(m.is_core)}
               for m in (await self.session.execute(
                   select(TaughtModule).where(TaughtModule.programme_id == programme_id)
                   .order_by(TaughtModule.code))).scalars().all()]
        seen = {x["moduleId"] for x in out}
        for m in (await self.session.execute(
                select(TaughtModule).join(ModuleOffering, ModuleOffering.module_id == TaughtModule.id)
                .where(ModuleOffering.programme_id == programme_id).order_by(TaughtModule.code)
        )).scalars().all():
            if str(m.id) not in seen:
                out.append({"moduleId": str(m.id), "code": m.code, "isCore": False})
        return out

    async def pin_for(self, student: Student, programme_id: uuid.UUID | None = None) -> ProgrammeVersion | None:
        pid = programme_id or student.programme_id
        if pid is None:
            return None
        pin = (await self.session.execute(
            select(StudentProgrammePin).where(StudentProgrammePin.student_id == student.id,
                                              StudentProgrammePin.programme_id == pid)
        )).scalar_one_or_none()
        if pin is None:
            return None
        return await self.session.get(ProgrammeVersion, pin.programme_version_id)

    # ---------------- writes (callers commit) ----------------

    async def initialise(self, programme: Programme, *, valid_from: date | None = None,
                         user_id: uuid.UUID | None = None) -> ProgrammeVersion:
        """Version 1 from the programme as it stands (no-op if it has versions)."""
        existing = await self.versions(programme.id)
        if existing:
            return existing[0]
        if valid_from is None:
            first_start = (await self.session.execute(
                select(func.min(Student.start_date)).where(Student.programme_id == programme.id)
            )).scalar()
            created = programme.created_at.date() if programme.created_at else fact_history.today()
            valid_from = min(_ay_start(first_start), _ay_start(created)) if first_start else _ay_start(created)
        v = ProgrammeVersion(
            programme_id=programme.id, version_no=1, valid_from=valid_from, valid_to=None,
            taught_total_credits=programme.taught_total_credits, duration_months=programme.duration_months,
            grading_policy=programme.grading_policy, structure=await self.live_structure(programme.id),
            change_note="First version", created_by_user_id=user_id,
        )
        if getattr(programme, "tenant_id", None) is not None:
            v.tenant_id = programme.tenant_id
        self.session.add(v)
        await self.session.flush()
        return v

    async def ensure_pin(self, student: Student, programme_id: uuid.UUID | None = None, *,
                         on: date | None = None) -> ProgrammeVersion | None:
        """Pin the student to the version in force on ``on`` (the day they started on the
        programme). An existing pin is never moved."""
        pid = programme_id or student.programme_id
        if pid is None:
            return None
        current = await self.pin_for(student, pid)
        if current is not None:
            return current
        programme = await self.session.get(Programme, pid)
        if programme is None:
            return None
        day = on or student.start_date or fact_history.today()
        version = await self.version_at(pid, day) or await self.initialise(programme)
        pin = StudentProgrammePin(student_id=student.id, programme_id=pid,
                                  programme_version_id=version.id, pinned_on=day)
        if getattr(student, "tenant_id", None) is not None:
            pin.tenant_id = student.tenant_id
        self.session.add(pin)
        await self.session.flush()
        return version

    async def sync_structure(self, programme_id: uuid.UUID) -> None:
        """After the programme's modules changed: the latest version takes the new structure. If
        students are pinned to it, it may only gain modules (CMA)."""
        vs = await self.versions(programme_id)
        if not vs:
            return
        latest = vs[-1]
        live = await self.live_structure(programme_id)
        if not await self.pinned_count(latest.id):
            latest.structure = live
            return
        now = {x["moduleId"]: x for x in live}
        removed = [x["code"] for x in latest.structure if x["moduleId"] not in now]
        demoted = [x["code"] for x in latest.structure
                   if x.get("isCore") and x["moduleId"] in now and not now[x["moduleId"]]["isCore"]]
        if removed or demoted:
            what = ", ".join(f"remove {c}" for c in removed) + (", " if removed and demoted else "") + \
                ", ".join(f"make {c} optional" for c in demoted)
            raise ConflictError(
                f"Students are on {label(latest)} of this programme, so its modules can't change that "
                f"way ({what}) — the CMA rule. Create a new programme version from the date it "
                "applies; current students keep theirs."
            )
        have = {x["moduleId"] for x in latest.structure}
        latest.structure = list(latest.structure) + [x for x in live if x["moduleId"] not in have]

    async def guard_rules(self, programme: Programme, patch: dict) -> None:
        """Before editing a programme's rules: apply them to today's version, or refuse if
        students are pinned to it."""
        changes = {k: v for k, v in patch.items() if k in RULE_FIELDS and getattr(programme, k) != v}
        if not changes:
            return
        current = await self.version_at(programme.id, fact_history.today())
        if current is None:
            return   # no versions yet: the first one will take the edited values
        if await self.pinned_count(current.id):
            raise ConflictError(
                f"Students are on {label(current)} of {programme.code}, so its "
                f"{', '.join(k.replace('_', ' ') for k in changes)} can't change (CMA). Create a new "
                "programme version from the date the change applies."
            )
        for k, v in changes.items():
            setattr(current, k, v)

    async def new_version(self, programme: Programme, *, effective_from: date, changes: dict,
                          note: str | None, user_id: uuid.UUID | None) -> ProgrammeVersion:
        if not (note or "").strip():
            raise WorkflowError("Say what changed and why — it is shown against the version")
        vs = await self.versions(programme.id) or [await self.initialise(programme)]
        last = vs[-1]
        if last.valid_to is not None:
            raise WorkflowError(f"{programme.code} has no open version to replace")
        if effective_from <= last.valid_from:
            raise WorkflowError(
                f"The new version must start after the current one ({label(last)} from {last.valid_from})"
            )
        last.valid_to = effective_from
        rules = {k: getattr(last, k) for k in RULE_FIELDS}
        rules.update({k: v for k, v in changes.items() if k in RULE_FIELDS and v is not None})
        v = ProgrammeVersion(programme_id=programme.id, version_no=last.version_no + 1,
                             valid_from=effective_from, valid_to=None, **rules,
                             structure=list(last.structure), change_note=note.strip(),
                             created_by_user_id=user_id)
        if getattr(programme, "tenant_id", None) is not None:
            v.tenant_id = programme.tenant_id
        self.session.add(v)
        await self.session.flush()
        await self.refresh_cache(programme)
        return v

    async def refresh_cache(self, programme: Programme) -> bool:
        v = await self.version_at(programme.id, fact_history.today())
        if v is None:
            return False
        changed = False
        for k in RULE_FIELDS:
            if getattr(programme, k) != getattr(v, k):
                setattr(programme, k, getattr(v, k))
                changed = True
        return changed

    async def refresh_due(self) -> int:
        n = 0
        for p in (await self.session.execute(select(Programme))).scalars().all():
            n += int(await self.refresh_cache(p))
        if n:
            await self.session.flush()
        return n

    # ---------------- output ----------------

    async def overview(self, programme_id: uuid.UUID) -> dict:
        programme = await self.session.get(Programme, programme_id)
        if programme is None:
            raise NotFoundError("Programme not found")
        today = fact_history.today()
        out = []
        for v in await self.versions(programme_id):
            n = await self.pinned_count(v.id)
            out.append({
                "id": str(v.id), "versionNo": v.version_no, "label": label(v),
                "validFrom": v.valid_from.isoformat(),
                "validTo": v.valid_to.isoformat() if v.valid_to else None,
                "taughtTotalCredits": v.taught_total_credits, "durationMonths": v.duration_months,
                "gradingPolicy": v.grading_policy, "structure": v.structure,
                "changeNote": v.change_note, "students": n, "locked": n > 0, "current": _covers(v, today),
            })
        return {"programmeId": str(programme.id), "code": programme.code, "versions": out}
