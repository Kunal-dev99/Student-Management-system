"""Student record HTTP endpoints (arch §11.5 — student record).

Reads are row-scoped from the principal (arch §12.3): a supervisor sees only students they
currently supervise; broad roles see all.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import student_scope
from app.core.dependencies import get_current_principal, require_permission
from app.core.errors import ValidationAppError
from app.core.pagination import PageParams, list_envelope, page_params
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
)
from app.modules.student_record.custom_fields import CustomFieldService
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
    IntensityPreviewRequest,
    LifecycleDecision,
    LifecycleEventOut,
    LifecycleEventRequest,
    ProgrammeCreate,
    ProgrammeOut,
    ProgrammeUpdate,
    ResearchProjectOut,
    ReturnRequest,
    StudentOut,
    StudentSummary,
    StudentUpdate,
)
from app.modules.student_record.service import StudentService

router = APIRouter(prefix="/students", tags=["student"])
programmes_router = APIRouter(prefix="/programmes", tags=["student"])
lifecycle_router = APIRouter(prefix="/lifecycle-events", tags=["student"])


def _svc(session: AsyncSession) -> StudentService:
    return StudentService(StudentRepository(session))


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

def _custom_field_out(f) -> dict:
    return {
        "id": str(f.id), "key": f.key, "label": f.label, "dataType": f.data_type,
        "reason": f.reason, "sourcePath": f"custom.{f.key}",
        "createdAt": f.created_at.isoformat() if f.created_at else None,
    }


@router.get("/custom-fields", summary="List admin-defined custom student attributes")
async def list_custom_fields(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[dict]:
    return [_custom_field_out(f) for f in await CustomFieldService(session).list_fields()]


@router.post("/custom-fields", status_code=201, summary="Create a custom student attribute")
async def create_custom_field(
    body: dict,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    field = await CustomFieldService(session).create_field(
        label=(body or {}).get("label", ""),
        data_type=(body or {}).get("dataType", "string"),
        reason=(body or {}).get("reason", ""),
        user_id=principal.user_id,
    )
    return _custom_field_out(field)


@router.delete("/custom-fields/{field_id}", status_code=204, response_class=Response,
               summary="Delete a custom student attribute and its values")
async def delete_custom_field(
    field_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
):
    await CustomFieldService(session).delete_field(field_id)
    return Response(status_code=204)


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
    filled = await CustomFieldService(session).set_values(
        field_id, entries=(body or {}).get("values", []), user_id=principal.user_id,
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
    out: list[LifecycleEventOut] = []
    for e in events:
        row = svc.out(e)
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
    return await LifecycleService(session).approve_event(
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
