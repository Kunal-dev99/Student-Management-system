"""Export HTTP endpoints (arch §11.5, §13.4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_session
from app.modules.exports.schemas import ExportJobOut, ExportRequest
from app.modules.exports.service import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportJobOut, status_code=201, summary="Start an export job")
async def create_export(
    body: ExportRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> ExportJobOut:
    return ExportJobOut.model_validate(await ExportService(session).create_and_run(body.kind))


@router.get("", response_model=list[ExportJobOut], summary="Recent export jobs")
async def list_exports(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> list[ExportJobOut]:
    return [ExportJobOut.model_validate(j) for j in await ExportService(session).list_recent()]


@router.get("/{job_id}", response_model=ExportJobOut, summary="Export job status")
async def get_export(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> ExportJobOut:
    return ExportJobOut.model_validate(await ExportService(session).get(job_id))


@router.get("/{job_id}/download", summary="Download the export file")
async def download_export(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
):
    job = await ExportService(session).get(job_id)
    content = job.content or ""
    return Response(
        content=content, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{job.filename or "export.csv"}"'},
    )


# --- Phase 6.6 — statutory reporting profiles (configuration, not code) ---

class ProfileCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    code: str
    name: str
    academic_year: str
    description: str | None = None


class FieldCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    target_field: str
    source_expression: str
    position: int | None = None
    transform: str | None = None
    default_value: str | None = None
    required: bool = False
    allowed_values: list[str] | None = None


class CloneRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    academic_year: str


class FieldUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    target_field: str | None = None
    source_expression: str | None = None
    position: int | None = None
    transform: str | None = None
    default_value: str | None = None
    required: bool | None = None
    allowed_values: list[str] | None = None


class SignOffRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    notes: str | None = None


profiles_router = APIRouter(prefix="/report-profiles", tags=["exports"])


def _engine(session: AsyncSession):
    from app.modules.exports.statutory import StatutoryEngine

    return StatutoryEngine(session)


@profiles_router.get("", summary="Statutory report profiles")
async def list_profiles(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> list[dict]:
    return await _engine(session).list_profiles()


@profiles_router.get("/transforms", summary="Transforms a field mapping may use")
async def list_transforms(_=Depends(require_permission("reporting.read"))) -> dict:
    from app.modules.exports.statutory import TRANSFORMS

    return {"transforms": sorted(TRANSFORMS)}


@profiles_router.post("", status_code=201, summary="Create a statutory profile")
async def create_profile(
    body: ProfileCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    eng = _engine(session)
    p = await eng.create_profile(code=body.code, name=body.name,
                                 academic_year=body.academic_year, description=body.description)
    return eng.profile_out(p)


@profiles_router.get("/{profile_id}", summary="Profile with its field mappings")
async def profile_detail(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await _engine(session).profile_detail(profile_id)


@profiles_router.post("/{profile_id}/fields", status_code=201, summary="Map a field")
async def add_field(
    profile_id: uuid.UUID,
    body: FieldCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    eng = _engine(session)
    m = await eng.add_field(
        profile_id, target_field=body.target_field, source_expression=body.source_expression,
        position=body.position, transform=body.transform, default_value=body.default_value,
        required=body.required, allowed_values=body.allowed_values,
    )
    return eng.mapping_out(m)


@profiles_router.post("/{profile_id}/clone", status_code=201, summary="Carry a return to a new year")
async def clone_profile(
    profile_id: uuid.UUID,
    body: CloneRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    eng = _engine(session)
    return eng.profile_out(await eng.clone_profile(profile_id, academic_year=body.academic_year))


@profiles_router.get("/{profile_id}/validate", summary="Validation report without producing a file")
async def validate_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    result = await _engine(session).generate(profile_id)
    return {"profile": result["profile"], "rowCount": result["rowCount"],
            "validation": result["validation"]}


@profiles_router.post("/{profile_id}/generate", status_code=201, summary="Produce the statutory extract")
async def generate_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    from app.modules.exports.service import ExportService

    return await ExportService(session).run_statutory_profile(profile_id)


# --- F1 — sign-off, immutability, and mandatory-field gap report ---

@profiles_router.get("/{profile_id}/compile", summary="Missing mandatory fields vs. the published spec")
async def compile_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await _engine(session).compile(profile_id)


@profiles_router.patch("/{profile_id}/fields/{mapping_id}", summary="Edit a mapping (refused if signed off)")
async def update_field(
    profile_id: uuid.UUID,
    mapping_id: uuid.UUID,
    body: FieldUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    eng = _engine(session)
    m = await eng.update_field(
        profile_id, mapping_id,
        target_field=body.target_field, source_expression=body.source_expression,
        position=body.position, transform=body.transform,
        default_value=body.default_value, required=body.required,
        allowed_values=body.allowed_values,
    )
    return eng.mapping_out(m)


@profiles_router.delete("/{profile_id}/fields/{mapping_id}", status_code=204,
                        response_class=Response,
                        summary="Remove a mapping (refused if signed off)")
async def delete_field(
    profile_id: uuid.UUID,
    mapping_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
):
    await _engine(session).delete_field(profile_id, mapping_id)
    return Response(status_code=204)


@profiles_router.post("/{profile_id}/sign-off", summary="Attest the profile is complete (Registry / HESA owner)")
async def sign_off_profile(
    profile_id: uuid.UUID,
    body: SignOffRequest,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("reports.signoff")),
) -> dict:
    eng = _engine(session)
    profile = await eng.sign_off(profile_id, user_id=principal.user_id, notes=body.notes)
    return eng.profile_out(profile)


@profiles_router.post("/{profile_id}/unsign", summary="Unlock a signed-off profile for edits")
async def unsign_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reports.signoff")),
) -> dict:
    eng = _engine(session)
    return eng.profile_out(await eng.unsign(profile_id))
