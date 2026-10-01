"""Taught-lifecycle HTTP endpoints (ICR G1).

Module/assessment management is programme configuration (admin.configure). Enrolments, results,
dissertation and award are per-student and row-scoped exactly like progression/funding, guarded by
taught.read / taught.change.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.student_record.router import scoped_ids
from app.modules.taught.repository import TaughtRepository
from app.modules.taught.schemas import (
    AssessmentCreate,
    AssessmentOut,
    AwardOut,
    CondoneRequest,
    DissertationOut,
    DissertationUpsert,
    ElectiveCandidateOut,
    EnrolmentCreate,
    EnrolmentDatesRequest,
    EnrolmentOut,
    EnrolmentStatusRequest,
    EnrolmentWithdrawRequest,
    InterruptModulesRequest,
    LinkElectiveRequest,
    LinkProgrammeElectivesRequest,
    ModuleCreate,
    ModuleOut,
    ModuleUpdate,
    ResultRecord,
    TaughtRecordOut,
)
from app.modules.taught.module_history import ModuleStatusHistoryService
from app.modules.taught.service import TaughtService
from app.modules.student_record.periods import assert_backdate_allowed

programme_router = APIRouter(prefix="/programmes", tags=["taught"])
module_router = APIRouter(prefix="/taught-modules", tags=["taught"])
student_router = APIRouter(prefix="/students", tags=["taught"])
enrolment_router = APIRouter(prefix="/module-enrolments", tags=["taught"])


def _svc(session: AsyncSession) -> TaughtService:
    return TaughtService(TaughtRepository(session))


# --- Modules & assessments (programme configuration) ---

@programme_router.get("/{programme_id}/modules", response_model=list[ModuleOut], summary="List taught modules")
async def list_modules(
    programme_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("taught.read")),
) -> list[ModuleOut]:
    return [ModuleOut.model_validate(m) for m in await _svc(session).list_modules(programme_id)]


@programme_router.post("/{programme_id}/modules", response_model=ModuleOut, status_code=201, summary="Add a taught module")
async def create_module(
    programme_id: uuid.UUID,
    body: ModuleCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> ModuleOut:
    return ModuleOut.model_validate(await _svc(session).create_module(programme_id, body))


class CohortEnrolRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    academic_year: str | None = None
    student_ids: list[uuid.UUID] | None = None   # None = every student on the programme
    only_core: bool = True


@programme_router.post("/{programme_id}/enrol-cohort",
                       summary="Enrol a group of the programme's students on its (core) modules")
async def enrol_cohort(
    programme_id: uuid.UUID,
    body: CohortEnrolRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("taught.change")),
) -> dict:
    return await _svc(session).bulk_enrol_core(
        programme_id, academic_year=body.academic_year,
        student_ids=body.student_ids, only_core=body.only_core,
    )


@module_router.patch("/{module_id}", response_model=ModuleOut, summary="Update a taught module")
async def update_module(
    module_id: uuid.UUID,
    body: ModuleUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> ModuleOut:
    return ModuleOut.model_validate(await _svc(session).update_module(module_id, body))


@module_router.post("/{module_id}/assessments", response_model=AssessmentOut, status_code=201, summary="Add an assessment to a module")
async def add_assessment(
    module_id: uuid.UUID,
    body: AssessmentCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> AssessmentOut:
    return AssessmentOut.model_validate(await _svc(session).add_assessment(module_id, body))


# --- Shared / elective modules: offer another programme's modules here ---

@programme_router.get("/{programme_id}/available-electives", response_model=list[ElectiveCandidateOut],
                      summary="Modules from other programmes that can be added here as electives")
async def available_electives(
    programme_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("taught.read")),
) -> list[ElectiveCandidateOut]:
    return [ElectiveCandidateOut.model_validate(m)
            for m in await _svc(session).available_electives(programme_id)]


@programme_router.post("/{programme_id}/module-offerings", status_code=201,
                       summary="Offer another programme's module here as an elective")
async def link_elective(
    programme_id: uuid.UUID,
    body: LinkElectiveRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _svc(session).link_elective(programme_id, body.module_id)


@programme_router.post("/{programme_id}/module-offerings/from-programme",
                       summary="Offer ALL of another programme's modules here as electives")
async def link_programme_electives(
    programme_id: uuid.UUID,
    body: LinkProgrammeElectivesRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _svc(session).link_programme_electives(programme_id, body.source_programme_id)


@programme_router.delete("/{programme_id}/module-offerings/{module_id}",
                         summary="Stop offering an elective module here")
async def unlink_elective(
    programme_id: uuid.UUID,
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _svc(session).unlink_elective(programme_id, module_id)


# --- Enrolments & results (per student, row-scoped) ---

@student_router.get("/{student_id}/taught", response_model=TaughtRecordOut, summary="Taught record (enrolments, dissertation, award)")
async def taught_record(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.read")),
) -> TaughtRecordOut:
    allowed = await scoped_ids(principal, session)
    return TaughtRecordOut.model_validate(await _svc(session).taught_record(student_id, allowed_ids=allowed))


@student_router.get("/{student_id}/taught/summary",
                    summary="AI board assistant — grounded standing + recommended actions")
async def taught_board_summary(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    return await _svc(session).board_summary(student_id, allowed_ids=allowed)


@student_router.get("/{student_id}/module-enrolments", response_model=list[EnrolmentOut], summary="Student module enrolments")
async def list_enrolments(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.read")),
) -> list[EnrolmentOut]:
    allowed = await scoped_ids(principal, session)
    return [EnrolmentOut.model_validate(e) for e in await _svc(session).list_enrolments(student_id, allowed_ids=allowed)]


@student_router.post("/{student_id}/module-enrolments", response_model=EnrolmentOut, status_code=201, summary="Enrol a student on a module")
async def enrol(
    student_id: uuid.UUID,
    body: EnrolmentCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> EnrolmentOut:
    allowed = await scoped_ids(principal, session)
    return EnrolmentOut.model_validate(await _svc(session).enrol(student_id, body, allowed_ids=allowed))


@enrolment_router.post("/{enrolment_id}/results", response_model=EnrolmentOut, status_code=201, summary="Record an assessment result")
async def record_result(
    enrolment_id: uuid.UUID,
    body: ResultRecord,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> EnrolmentOut:
    return EnrolmentOut.model_validate(await _svc(session).record_result(enrolment_id, body, user_id=principal.user_id))


@enrolment_router.patch("/{enrolment_id}/status", response_model=EnrolmentOut, summary="Set an enrolment's status")
async def set_status(
    enrolment_id: uuid.UUID,
    body: EnrolmentStatusRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> EnrolmentOut:
    assert_backdate_allowed(body.effective_date, principal, what="This module status change")
    return EnrolmentOut.model_validate(await _svc(session).set_enrolment_status(
        enrolment_id, body.status, effective_date=body.effective_date, reason=body.reason,
        user_id=principal.user_id,
    ))


@enrolment_router.post("/{enrolment_id}/withdraw", response_model=EnrolmentOut,
                       summary="Withdraw the student from a module from a date (ends the module then)")
async def withdraw_from_module(
    enrolment_id: uuid.UUID,
    body: EnrolmentWithdrawRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> EnrolmentOut:
    assert_backdate_allowed(body.effective_date, principal, what="This module withdrawal")
    return EnrolmentOut.model_validate(await _svc(session).withdraw(
        enrolment_id, effective_date=body.effective_date, reason=body.reason, user_id=principal.user_id,
    ))


@enrolment_router.patch("/{enrolment_id}/dates", response_model=EnrolmentOut,
                        summary="Set the student's own start / end dates on a module")
async def set_module_dates(
    enrolment_id: uuid.UUID,
    body: EnrolmentDatesRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> EnrolmentOut:
    return EnrolmentOut.model_validate(await _svc(session).update_dates(
        enrolment_id, start_date=body.start_date, end_date=body.end_date, reason=body.reason,
        user_id=principal.user_id,
    ))


@enrolment_router.get("/{enrolment_id}/status-history", summary="A module enrolment's dated status history")
async def module_status_history(
    enrolment_id: uuid.UUID,
    include_superseded: bool = Query(False, alias="includeSuperseded"),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("taught.read")),
) -> list[dict]:
    hist = ModuleStatusHistoryService(session)
    rows = await (hist.all_rows(enrolment_id) if include_superseded else hist.live_rows(enrolment_id))
    return [hist.out(r) for r in rows]


@student_router.get("/{student_id}/open-modules", summary="Modules the student is still studying")
async def open_modules(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.read")),
) -> list[dict]:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    return await _svc(session).open_modules(student_id)


@student_router.post("/{student_id}/module-enrolments/interrupt", response_model=list[EnrolmentOut],
                     summary="Interrupt the chosen open modules (student suspended)")
async def interrupt_modules(
    student_id: uuid.UUID,
    body: InterruptModulesRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> list[EnrolmentOut]:
    assert_backdate_allowed(body.effective_date, principal, what="Interrupting these modules")
    rows = await _svc(session).interrupt_modules(
        student_id, effective_date=body.effective_date, enrolment_ids=body.enrolment_ids,
        reason=body.reason, user_id=principal.user_id, source_event_id=body.source_event_id,
    )
    return [EnrolmentOut.model_validate(r) for r in rows]


@enrolment_router.patch("/{enrolment_id}/condone", response_model=EnrolmentOut,
                        summary="Condone (or un-condone) a failed module — a board decision")
async def condone(
    enrolment_id: uuid.UUID,
    body: CondoneRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("taught.change")),
) -> EnrolmentOut:
    return EnrolmentOut.model_validate(await _svc(session).condone_module(enrolment_id, condoned=body.condoned))


# --- Dissertation ---

@student_router.get("/{student_id}/dissertation", response_model=DissertationOut | None, summary="Taught dissertation")
async def get_dissertation(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.read")),
):
    allowed = await scoped_ids(principal, session)
    rec = await _svc(session).taught_record(student_id, allowed_ids=allowed)
    return DissertationOut.model_validate(rec["dissertation"]) if rec["dissertation"] else None


@student_router.put("/{student_id}/dissertation", response_model=DissertationOut, summary="Create or update the dissertation")
async def upsert_dissertation(
    student_id: uuid.UUID,
    body: DissertationUpsert,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> DissertationOut:
    allowed = await scoped_ids(principal, session)
    return DissertationOut.model_validate(await _svc(session).upsert_dissertation(student_id, body, allowed_ids=allowed))


# --- Award / classification ---

@student_router.post("/{student_id}/taught-award", response_model=AwardOut, summary="Compute and record the classification")
async def compute_award(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("taught.change")),
) -> AwardOut:
    allowed = await scoped_ids(principal, session)
    return AwardOut.model_validate(
        await _svc(session).compute_award(student_id, user_id=principal.user_id, allowed_ids=allowed)
    )
