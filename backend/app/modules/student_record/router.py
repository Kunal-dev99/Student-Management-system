"""Student record HTTP endpoints (arch §11.5 — student record).

Reads are row-scoped from the principal (arch §12.3): a supervisor sees only students they
currently supervise; broad roles see all.
"""
from __future__ import annotations

import uuid

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import student_scope
from app.core.dependencies import get_current_principal, require_any_permission, require_permission
from app.core.errors import NotFoundError, PermissionError, ValidationAppError
from app.core.pagination import PageParams, list_envelope, page_params
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
)
from app.modules.student_record.custom_fields import CustomFieldService
from app.modules.student_record.custom_fields import Status as CustomStatus
from app.modules.student_record.import_service import (
    DEFAULT_IMPORT_TEMPLATE,
    CohortImportService,
    ImportDefaults,
    sanitize_template,
)
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.lifecycle import LifecycleService
from app.modules.student_record.schemas import (
    EnrolRequest,
    FactChangeRequest,
    ProgrammeVersionRequest,
    IntensityPreviewRequest,
    LifecycleDecision,
    LifecycleEventOut,
    LifecycleEventRequest,
    ProgrammeCreate,
    ProgrammeOut,
    ProgrammeUpdate,
    ResearchProjectOut,
    ReturnRequest,
    StatusCorrectionRequest,
    StudentOut,
    StudentSummary,
    StudentUpdate,
)
from app.modules.student_record.models import Student, StudentStatusHistory
from app.modules.student_record.service import StudentService
from app.modules.student_record.periods import assert_backdate_allowed
from app.modules.student_record.retrospective import signed_off_returns, warnings_for
from app.modules.student_record.status_history import StatusHistoryService
from app.modules.student_record.timeline import StudentTimeline

router = APIRouter(prefix="/students", tags=["student"])
programmes_router = APIRouter(prefix="/programmes", tags=["student"])
lifecycle_router = APIRouter(prefix="/lifecycle-events", tags=["student"])


def _svc(session: AsyncSession) -> StudentService:
    return StudentService(StudentRepository(session))


@programmes_router.get("/{programme_id}/versions",
                       summary="A programme's dated versions and how many students are on each (Phase 8b)")
async def programme_versions(
    programme_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    from app.modules.student_record.programme_versions import ProgrammeVersionService

    return await ProgrammeVersionService(session).overview(programme_id)


@programmes_router.post("/{programme_id}/versions", status_code=201,
                        summary="A new programme version from a date (current students keep theirs)")
async def new_programme_version(
    programme_id: uuid.UUID,
    body: ProgrammeVersionRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    from app.modules.student_record.models import Programme
    from app.modules.student_record.programme_versions import ProgrammeVersionService

    programme = await session.get(Programme, programme_id)
    if programme is None:
        raise NotFoundError("Programme not found")
    svc = ProgrammeVersionService(session)
    await svc.new_version(programme, effective_from=body.effective_from,
                          changes=body.model_dump(include={"taught_total_credits", "duration_months",
                                                           "grading_policy"}),
                          note=body.note, user_id=principal.user_id)
    await session.commit()
    return await svc.overview(programme_id)


@programmes_router.get("", response_model=list[ProgrammeOut], summary="List programmes")
async def list_programmes(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[ProgrammeOut]:
    rows = await _svc(session).list_programmes()
    return [ProgrammeOut.model_validate(p) for p in rows]


@programmes_router.post("", response_model=ProgrammeOut, status_code=201, summary="Create a programme")
async def create_programme(
    body: ProgrammeCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> ProgrammeOut:
    return ProgrammeOut.model_validate(await _svc(session).create_programme(body))


@programmes_router.patch("/{programme_id}", response_model=ProgrammeOut, summary="Update a programme")
async def update_programme(
    programme_id: uuid.UUID,
    body: ProgrammeUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> ProgrammeOut:
    prog = await _svc(session).update_programme(programme_id, body.model_dump(exclude_unset=True))
    return ProgrammeOut.model_validate(prog)


async def scoped_ids(principal: Principal, session: AsyncSession) -> list[uuid.UUID] | None:
    """Resolve the student ids this principal may see (None = unrestricted)."""
    scope = student_scope(principal)
    if scope.kind == "all":
        return None
    if scope.kind == "supervisor" and scope.person_id is not None:
        from app.modules.supervision.repository import SupervisionRepository
        from app.modules.supervision.service import SupervisionService

        return await SupervisionService(
            SupervisionRepository(session)
        ).supervised_student_ids(scope.person_id)
    if scope.kind == "self" and scope.person_id is not None:
        student = await StudentRepository(session).get_by_person(scope.person_id)
        return [student.id] if student else []
    return []  # no scope -> sees nothing


@router.get("", summary="List students (row-scoped)")
async def list_students(
    page: PageParams = Depends(page_params),
    search: str | None = Query(None, description="match student ref or person name"),
    status: StudentStatus | None = Query(None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    rows, total = await _svc(session).list_students(
        limit=page.limit, offset=page.offset, allowed_ids=allowed, search=search, status=status
    )
    # One batch lookup for the page's person names — the register is read by
    # humans, and humans find students by name, not by reference.
    from sqlalchemy import select

    from app.modules.person.models import Person

    person_ids = {s.person_id for s in rows}
    names: dict = {}
    if person_ids:
        people = (await session.execute(select(Person).where(Person.id.in_(person_ids)))).scalars()
        names = {p.id: f"{p.given_name} {p.family_name}" for p in people}
    data = [
        {**StudentOut.model_validate(s).model_dump(by_alias=True),
         "personName": names.get(s.person_id)}
        for s in rows
    ]
    return list_envelope(data, limit=page.limit, total=total)


@router.post("/enrol", response_model=StudentOut, status_code=201,
             summary="Enrol an already-accepted student (no recruitment funnel)")
async def enrol_student(
    body: EnrolRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> StudentOut:
    student = await _svc(session).enrol(
        person_id=body.person_id,
        person_data=body.person,
        programme_id=body.programme_id,
        department_id=body.department_id,
        research_area_id=body.research_area_id,
        research_topic=body.research_topic,
        start_date=body.start_date,
        study_mode=body.study_mode,
        status=body.status,
        expected_end_date=body.expected_end_date,
        funding=body.funding,
    )
    return StudentOut.model_validate(student)


async def _read_csv(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise ValidationAppError("The file is empty.")
    if len(data) > 5 * 1024 * 1024:
        raise ValidationAppError("File too large (limit 5 MB).")
    return data


def _defaults(programme: str | None, start_date: str | None, funder: str | None) -> ImportDefaults:
    return ImportDefaults(
        programme_code=(programme or "").strip() or None,
        start_date=(start_date or "").strip() or None,
        funder=(funder or "").strip() or None,
    )


@router.post("/import/preview", summary="Validate a cohort CSV without writing anything")
async def import_preview(
    file: UploadFile = File(...),
    default_programme: str | None = Form(None),
    default_start_date: str | None = Form(None),
    default_funder: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> dict:
    return await CohortImportService(session).preview(
        await _read_csv(file), _defaults(default_programme, default_start_date, default_funder)
    )


@router.post("/import/commit", status_code=201, summary="Enrol a cohort from CSV (idempotent on ref)")
async def import_commit(
    file: UploadFile = File(...),
    default_programme: str | None = Form(None),
    default_start_date: str | None = Form(None),
    default_funder: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> dict:
    return await CohortImportService(session).commit(
        await _read_csv(file), _defaults(default_programme, default_start_date, default_funder)
    )


IMPORT_TEMPLATE_KEY = "cohort_import_template"


async def _load_import_template(session: AsyncSession) -> list[dict]:
    from sqlalchemy import select as _select

    from app.modules.settings.models import InstitutionSetting

    row = (
        await session.execute(
            _select(InstitutionSetting).where(InstitutionSetting.key == IMPORT_TEMPLATE_KEY)
        )
    ).scalar_one_or_none()
    cols = (row.value or {}).get("columns") if row else None
    return sanitize_template(cols) if cols else list(DEFAULT_IMPORT_TEMPLATE)


@router.get("/import/template", summary="Cohort import template (which columns appear)")
async def get_import_template(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> dict:
    return {"columns": await _load_import_template(session)}


@router.put("/import/template", summary="Configure the cohort import template")
async def set_import_template(
    body: dict,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    from sqlalchemy import select as _select

    from app.modules.settings.models import InstitutionSetting

    cols = sanitize_template((body or {}).get("columns"))
    if not any(c["enabled"] for c in cols):
        raise ValidationAppError("At least one column must be enabled.")
    required_disabled = [c["field"] for c in cols if c["required"] and not c["enabled"]]
    if required_disabled:
        raise ValidationAppError("A required column cannot be disabled: " + ", ".join(required_disabled))
    row = (
        await session.execute(
            _select(InstitutionSetting).where(InstitutionSetting.key == IMPORT_TEMPLATE_KEY)
        )
    ).scalar_one_or_none()
    if row is not None:
        row.value = {"columns": cols}
        row.updated_by_user_id = principal.user_id
    else:
        session.add(
            InstitutionSetting(
                key=IMPORT_TEMPLATE_KEY,
                value={"columns": cols},
                updated_by_user_id=principal.user_id,
            )
        )
    await session.commit()
    return {"columns": cols}


# --- Admin-defined custom student attributes (HESA gap capture) --------------------------------
# Declared before /{student_id} so "custom-fields" isn't captured as a student id.

def _custom_field_out(f, emails: dict | None = None) -> dict:
    emails = emails or {}
    return {
        "id": str(f.id), "key": f.key, "label": f.label, "dataType": f.data_type,
        "reason": f.reason, "sourcePath": f"custom.{f.key}",
        "trackHistory": bool(f.track_history),
        "status": f.status,
        "requestedBy": str(f.created_by_user_id) if f.created_by_user_id else None,
        "requestedByEmail": emails.get(f.created_by_user_id),
        "decidedBy": str(f.decided_by_user_id) if f.decided_by_user_id else None,
        "decidedByEmail": emails.get(f.decided_by_user_id),
        "decidedAt": f.decided_at.isoformat() if f.decided_at else None,
        "decisionReason": f.decision_reason,
        "createdAt": f.created_at.isoformat() if f.created_at else None,
    }


def _custom_event_out(e) -> dict:
    return {
        "id": str(e.id), "customFieldId": str(e.custom_field_id) if e.custom_field_id else None,
        "key": e.field_key, "label": e.field_label, "action": e.action,
        "fromStatus": e.from_status, "toStatus": e.to_status,
        "actorEmail": e.actor_email, "notes": e.notes, "detail": e.detail,
        "at": e.created_at.isoformat() if e.created_at else None,
    }


async def _user_emails(session: AsyncSession, fields) -> dict:
    from sqlalchemy import select

    from app.modules.identity.models import User

    ids = {i for f in fields for i in (f.created_by_user_id, f.decided_by_user_id) if i}
    if not ids:
        return {}
    return dict((await session.execute(select(User.id, User.email).where(User.id.in_(ids)))).all())


async def _fields_out(session: AsyncSession, fields) -> list[dict]:
    emails = await _user_emails(session, fields)
    return [_custom_field_out(f, emails) for f in fields]


class CustomAttributeRequestIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    dataType: str = "string"
    reason: str = Field(min_length=1)
    trackHistory: bool = False


class CustomAttributeDecisionIn(BaseModel):
    reason: str | None = None
    # Approve only: make it live straight away (records approve then activate).
    activate: bool = False


_GOVERNANCE = ("custom_attribute.request", "custom_attribute.approve")


def _statuses(raw: str | None) -> tuple[str, ...] | None:
    return tuple(s.strip() for s in raw.split(",") if s.strip()) if raw else None


@router.get("/custom-fields", summary="Live custom student attributes (the ones that take values)")
async def list_custom_fields(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[dict]:
    return await _fields_out(session, await CustomFieldService(session).list_fields(CustomStatus.LIVE))


@router.get("/custom-attributes", summary="Custom attribute catalogue, filterable by status")
async def list_custom_attributes(
    status: str | None = Query(None, description="Comma-separated: pending, approved, rejected, "
                                                 "active, review, retired. Default: live (active, review)."),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[dict]:
    wanted = _statuses(status) or CustomStatus.LIVE
    # Requests that were never made live are governance business, not something every reader sees.
    if set(wanted) - set(CustomStatus.LIVE) and not any(principal.has_permission(c) for c in _GOVERNANCE):
        raise PermissionError("Missing permission: custom_attribute.request")
    return await _fields_out(session, await CustomFieldService(session).list_fields(wanted))


@router.post("/custom-attribute-requests", status_code=201, summary="Request a new custom student attribute")
async def request_custom_attribute(
    body: CustomAttributeRequestIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("custom_attribute.request")),
) -> dict:
    field = await CustomFieldService(session).request_field(
        label=body.label, data_type=body.dataType, reason=body.reason, principal=principal,
        track_history=body.trackHistory,
    )
    return (await _fields_out(session, [field]))[0]


@router.get("/custom-attribute-requests", summary="Attribute requests (default: pending, approved, rejected)")
async def list_custom_attribute_requests(
    status: str | None = Query(None, description="Comma-separated statuses"),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_any_permission(*_GOVERNANCE)),
) -> list[dict]:
    wanted = _statuses(status) or (CustomStatus.PENDING, CustomStatus.APPROVED, CustomStatus.REJECTED)
    return await _fields_out(session, await CustomFieldService(session).list_fields(wanted))


@router.get("/custom-attribute-events", summary="Decision trail across all custom attributes")
async def list_custom_attribute_events(
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_any_permission(*_GOVERNANCE)),
) -> list[dict]:
    return [_custom_event_out(e) for e in await CustomFieldService(session).events(limit=limit)]


@router.get("/custom-attribute-requests/{field_id}", summary="One attribute request with its decision trail")
async def get_custom_attribute_request(
    field_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_any_permission(*_GOVERNANCE)),
) -> dict:
    svc = CustomFieldService(session)
    out = (await _fields_out(session, [await svc.get_field(field_id)]))[0]
    out["events"] = [_custom_event_out(e) for e in await svc.events(field_id)]
    return out


@router.post("/custom-attribute-requests/{field_id}/approve", summary="Approve a request (not your own)")
async def approve_custom_attribute(
    field_id: uuid.UUID,
    body: CustomAttributeDecisionIn | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("custom_attribute.approve")),
) -> dict:
    body = body or CustomAttributeDecisionIn()
    field = await CustomFieldService(session).approve(
        field_id, principal=principal, reason=body.reason, activate=body.activate,
    )
    return (await _fields_out(session, [field]))[0]


@router.post("/custom-attribute-requests/{field_id}/reject", summary="Reject a request (reason required)")
async def reject_custom_attribute(
    field_id: uuid.UUID,
    body: CustomAttributeDecisionIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("custom_attribute.approve")),
) -> dict:
    field = await CustomFieldService(session).reject(field_id, principal=principal, reason=body.reason or "")
    return (await _fields_out(session, [field]))[0]


@router.post("/custom-attribute-requests/{field_id}/activate", summary="Make an approved attribute live")
async def activate_custom_attribute(
    field_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("custom_attribute.approve")),
) -> dict:
    field = await CustomFieldService(session).activate(field_id, principal=principal)
    return (await _fields_out(session, [field]))[0]


@router.delete("/custom-attribute-requests/{field_id}", status_code=204, response_class=Response,
               summary="Withdraw a pending request")
async def withdraw_custom_attribute(
    field_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_any_permission(*_GOVERNANCE)),
):
    svc = CustomFieldService(session)
    field = await svc.get_field(field_id)
    # The requester withdraws their own; a checker may clear any pending request.
    if field.created_by_user_id != principal.user_id and not principal.has_permission("custom_attribute.approve"):
        raise PermissionError("Only the requester or an approver can withdraw this request.")
    await svc.withdraw(field_id, principal=principal)
    return Response(status_code=204)


@router.post("/custom-fields/{field_id}/track-history", summary="Start keeping dated history (one-way)")
async def enable_custom_field_history(
    field_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    field = await CustomFieldService(session).enable_history(field_id, user_id=principal.user_id)
    return (await _fields_out(session, [field]))[0]

# There is deliberately no hard delete of an attribute: decided attributes are kept for the record
# and active ones hold student data. A pending request is withdrawn (above).


@router.get("/custom-fields/{field_id}/values",
            summary="Every student with their value for this attribute (entry grid)")
async def get_custom_field_values(
    field_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    svc = CustomFieldService(session)
    field = await svc.get_field(field_id)
    return {"field": _custom_field_out(field), "rows": await svc.field_values(field_id)}


@router.put("/custom-fields/{field_id}/values", summary="Enter/update values per student")
async def set_custom_field_values(
    field_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> dict:
    raw_date = (body or {}).get("effectiveDate")
    try:
        on = date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        raise ValidationAppError("effectiveDate must be YYYY-MM-DD") from None
    svc = CustomFieldService(session)
    if (await svc.get_field(field_id)).track_history:
        await assert_backdate_allowed(session, on, principal, what="This attribute value")
    filled = await svc.set_values(
        field_id, entries=(body or {}).get("values", []), user_id=principal.user_id, effective_date=on,
    )
    return {"filled": filled}


@router.get("/{student_id}", response_model=StudentOut, summary="Get a student (row-scoped)")
async def get_student(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> StudentOut:
    allowed = await scoped_ids(principal, session)
    svc = _svc(session)
    student = await svc.get_student(student_id, allowed_ids=allowed)
    # Direct-enrol vs funnel — drives the journey tracker's Applicant stage (ICR G2).
    student.from_application = await svc.person_has_application(student.person_id)
    # Phase 8b — the programme version the student is on (CMA).
    from app.modules.student_record.programme_versions import ProgrammeVersionService, label
    student.programme_version = label(await ProgrammeVersionService(session).pin_for(student))
    # Phase 9 — today's unit of assessment, readable.
    if student.uoa_id is not None:
        from app.modules.student_record.models import UnitOfAssessment
        u = await session.get(UnitOfAssessment, student.uoa_id)
        student.uoa = f"{u.code} {u.name}" if u else None
    return StudentOut.model_validate(student)


@router.patch("/{student_id}", response_model=StudentOut, summary="Update a student")
async def update_student(
    student_id: uuid.UUID,
    body: StudentUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> StudentOut:
    student = await _svc(session).update_student(student_id, body.model_dump(exclude_unset=True))
    return StudentOut.model_validate(student)


@router.get("/{student_id}/project", response_model=ResearchProjectOut | None, summary="Research project")
async def get_project(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
):
    allowed = await scoped_ids(principal, session)
    student = await _svc(session).get_student(student_id, allowed_ids=allowed)
    return ResearchProjectOut.model_validate(student.project) if student.project else None


@router.get("/{student_id}/summary", response_model=StudentSummary, summary="Journey summary")
async def get_summary(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> StudentSummary:
    allowed = await scoped_ids(principal, session)
    return StudentSummary.model_validate(await _svc(session).summary(student_id, allowed_ids=allowed))


# --- Phase 6.5 — PGR exception lifecycle (suspension / extension / mode change) ---

@router.get("/{student_id}/lifecycle-events", response_model=list[LifecycleEventOut],
            summary="Suspensions, extensions and mode changes")
async def list_lifecycle_events(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[LifecycleEventOut]:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    svc = LifecycleService(session)
    events = await svc.events_for_student(student_id)
    student = None
    returns = None
    out: list[LifecycleEventOut] = []
    for e in events:
        row = svc.out(e)
        # Effective dating, Phase 5 — would approving this reach a signed-off return?
        if e.status is LifecycleEventStatus.requested and e.event_type is not LifecycleEventType.extension:
            if student is None:
                student = await svc._get_student(student_id)
            if returns is None:
                returns = await signed_off_returns(session)
            end = e.end_date if e.event_type is LifecycleEventType.suspension else None
            row["retrospective"] = await warnings_for(session, student, e.start_date, end, returns=returns)
        # ICR G6 — attach a deterministic impact preview to a PENDING date-moving request, so the
        # table and the approver see what it will do before deciding (not just intensity changes:
        # a mode change or extension that showed no effect until approval read as a broken app).
        if e.status is LifecycleEventStatus.requested:
            if e.event_type is LifecycleEventType.intensity_change and e.intensity_pct:
                if student is None:
                    student = await svc._get_student(student_id)
                row["impact"] = await svc.intensity_impact_preview(
                    student, prev_pct=e.previous_intensity_pct or await svc._current_intensity(student),
                    new_pct=e.intensity_pct, effective=e.start_date,
                )
            elif e.event_type in (LifecycleEventType.mode_change, LifecycleEventType.extension):
                if student is None:
                    student = await svc._get_student(student_id)
                row["impact"] = await svc.event_impact_preview(student, e)
        out.append(LifecycleEventOut.model_validate(row))
    return out


@router.post("/{student_id}/lifecycle-events", response_model=LifecycleEventOut, status_code=201,
             summary="Request a suspension, extension or mode change")
async def request_lifecycle_event(
    student_id: uuid.UUID,
    body: LifecycleEventRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> LifecycleEventOut:
    svc = LifecycleService(session)
    event = await svc.request_event(
        student_id, event_type=body.event_type, reason=body.reason,
        start_date=body.start_date, end_date=body.end_date,
        extension_days=body.extension_days, new_mode=body.new_mode,
        intensity_pct=body.intensity_pct,
        new_programme_id=body.new_programme_id,
        leave_category=body.leave_category,
        leaver_reason=body.leaver_reason,
        requested_by_user_id=principal.user_id,
    )
    return LifecycleEventOut.model_validate(svc.out(event))


@router.get("/{student_id}/intensity", summary="Study intensity (FTE %) timeline")
async def student_intensity(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return {"studentId": str(student_id), "currentPct": None, "periods": []}
    return await LifecycleService(session).intensity_overview(student_id)


@router.post("/{student_id}/intensity/impact-preview",
             summary="Preview a study-intensity change (deterministic, no write)")
async def intensity_impact_preview(
    student_id: uuid.UUID,
    body: IntensityPreviewRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> dict:
    if not 1 <= body.intensity_pct <= 100:
        raise ValidationAppError("Study intensity must be between 1 and 100%.")
    svc = LifecycleService(session)
    student = await svc._get_student(student_id)
    prev = await svc._current_intensity(student)
    return await svc.intensity_impact_preview(
        student, prev_pct=prev, new_pct=body.intensity_pct, effective=body.effective_date,
    )


@router.post("/{student_id}/return", summary="Record a return from suspension")
async def record_return(
    student_id: uuid.UUID,
    body: ReturnRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> dict:
    return await LifecycleService(session).record_return(
        student_id, returned_on=body.returned_on if body else None
    )


# --- Effective dating — status history ---

@router.get("/{student_id}/status-history", summary="Status history (effective-dated periods)")
async def status_history(
    student_id: uuid.UUID,
    include_superseded: bool = Query(False, alias="includeSuperseded"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[dict]:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    hist = StatusHistoryService(session)
    rows = await (hist.all_rows(student_id) if include_superseded else hist.live_rows(student_id))
    return [hist.out(r) for r in rows]


@router.post("/{student_id}/status-history/{row_id}/correct",
             summary="Correct a status period recorded wrongly (kept for audit, superseded)")
async def correct_status_history(
    student_id: uuid.UUID,
    row_id: uuid.UUID,
    body: StatusCorrectionRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.history.correct")),
) -> dict:
    hist = StatusHistoryService(session)
    row = await session.get(StudentStatusHistory, row_id)
    if row is None or row.student_id != student_id:
        raise NotFoundError("Status history row not found for this student")
    fixed = await hist.correct(row_id, valid_from=body.valid_from, status=body.status,
                               reason=body.reason, user_id=principal.user_id)
    student = await session.get(Student, student_id)
    await session.commit()
    return {"row": hist.out(fixed), "studentStatus": student.status.value}


# --- Effective dating, Phase 5 — history tab, as-of view, retrospective check ---

@router.get("/{student_id}/history", summary="Every dated fact for a student, with who recorded it and when")
async def student_history(
    student_id: uuid.UUID,
    include_superseded: bool = Query(False, alias="includeSuperseded"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        raise NotFoundError("Student not found")
    return await StudentTimeline(session).history(student_id, include_superseded=include_superseded)


@router.post("/{student_id}/facts/{fact}",
             summary="Record a dated fact (fee-status, study-location) from a date")
async def change_student_fact(
    student_id: uuid.UUID,
    fact: str,
    body: FactChangeRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> dict:
    from app.modules.student_record.fact_history import DIRECT_FACTS, today

    svc_cls = DIRECT_FACTS.get(fact)
    if svc_cls is None:
        raise NotFoundError(f"Unknown fact '{fact}' (expected one of: {', '.join(DIRECT_FACTS)})")
    on = body.effective_date or today()
    await assert_backdate_allowed(session, on, principal, what=f"This {svc_cls.label} change")
    student = await session.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found")
    svc = svc_cls(session)
    row = await svc.change(student, await svc.normalise(body.value), effective_from=on,
                           reason=(body.reason or "").strip() or None, user_id=principal.user_id)
    await session.commit()
    return {"row": svc.out(row), "current": getattr(student, svc.value_attr)}


@router.get("/{student_id}/facts/{fact}", summary="A dated fact's history (fee-status, study-location)")
async def student_fact_history(
    student_id: uuid.UUID,
    fact: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[dict]:
    from app.modules.student_record.fact_history import DIRECT_FACTS

    svc_cls = DIRECT_FACTS.get(fact)
    if svc_cls is None:
        raise NotFoundError(f"Unknown fact '{fact}'")
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    svc = svc_cls(session)
    return [svc.out(r) for r in await svc.live_rows(student_id)]


@router.get("/{student_id}/as-of", summary="The student's record as it stood on a date")
async def student_as_of(
    student_id: uuid.UUID,
    on: date = Query(..., alias="date"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        raise NotFoundError("Student not found")
    return await StudentTimeline(session).as_of(student_id, on)


@router.get("/{student_id}/retrospective-check",
            summary="Would a change from this date reach a signed-off return? (no write)")
async def retrospective_check(
    student_id: uuid.UUID,
    start: date = Query(..., alias="from"),
    end: date | None = Query(None, alias="to"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    from app.modules.student_record.periods import AMEND_PERMISSION

    student = await session.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found")
    warnings = await warnings_for(session, student, start, end)
    return {
        "from": start.isoformat(), "to": end.isoformat() if end else None,
        # A signed-off return covers this period: changing it is a data amendment.
        "closed": bool(warnings),
        "canAmend": principal.has_permission(AMEND_PERMISSION),
        "warnings": warnings,
    }


@lifecycle_router.get("/{event_id}/impact",
                      summary="AI-narrated impact of a pending intensity change (deterministic fallback)")
async def lifecycle_event_impact(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    return await LifecycleService(session).intensity_impact_narrated(event_id)


@lifecycle_router.post("/{event_id}/approve", summary="Approve — this is what moves the dates")
async def approve_lifecycle_event(
    event_id: uuid.UUID,
    body: LifecycleDecision | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.lifecycle.approve")),
) -> dict:
    svc = LifecycleService(session)
    event = await svc._get_event(event_id)
    end = event.end_date if event.event_type is LifecycleEventType.suspension else None
    await assert_backdate_allowed(session, event.start_date, principal, end=end,
                                  what=f"This {event.event_type.value.replace('_', ' ')}")
    return await svc.approve_event(
        event_id, approver_user_id=principal.user_id, note=body.note if body else None
    )


@lifecycle_router.post("/{event_id}/reject", summary="Reject a lifecycle request")
async def reject_lifecycle_event(
    event_id: uuid.UUID,
    body: LifecycleDecision | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.lifecycle.approve")),
) -> dict:
    return await LifecycleService(session).reject_event(
        event_id, approver_user_id=principal.user_id, note=body.note if body else None
    )
