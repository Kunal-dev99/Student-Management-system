"""Export HTTP endpoints (arch §11.5, §13.4)."""
from __future__ import annotations

import uuid

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_session
from app.modules.exports.schemas import (
    AdvisoryDecision,
    AdvisoryIngestRequest,
    ExportJobOut,
    ExportRequest,
)
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


class FromSpecRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    spec_key: str
    academic_year: str | None = None
    name: str | None = None


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
    """Human-facing catalog of transforms — each carries a plain-English label + description +
    category so the mapping form can group them and show something readable next to the code
    name. Also returns the legacy `transforms` flat list for older callers."""
    from app.modules.exports.statutory import TRANSFORMS
    from app.modules.exports.transforms_catalog import as_dict

    body = as_dict()
    return {**body, "transforms": sorted(TRANSFORMS)}


@profiles_router.get(
    "/record-schema",
    summary="Catalog of dotted source paths a field mapping may read from",
)
async def record_schema(_=Depends(require_permission("reporting.read"))) -> dict:
    """The authoritative list of source expressions available on the flat student record. Used by
    the mapping form to render a dropdown so admins never mistype a path."""
    from app.modules.exports.record_schema import as_dict

    return as_dict()


@profiles_router.get("/specs", summary="Published spec packs a profile can be created from")
async def list_specs(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    # Through the resolver so an accepted advisory's version shows in the picker (ICR G5).
    from app.modules.exports.spec_resolver import resolve_list_packs

    return {"specs": await resolve_list_packs(session)}


@profiles_router.post("/from-spec", status_code=201,
                      summary="Create a profile pre-mapped from a published spec (ICR G5)")
async def create_from_spec(
    body: FromSpecRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    eng = _engine(session)
    profile = await eng.from_spec(
        spec_key=body.spec_key, academic_year=body.academic_year, name=body.name,
    )
    return await eng.profile_detail(profile.id)


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


@profiles_router.get("/{profile_id}/fix-suggestions",
                     summary="Rule-based data-quality fixes for this return (suggest half)")
async def fix_suggestions(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await _engine(session).fix_suggestions(profile_id)


class ApplyFixRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    field: str
    transform: str


@profiles_router.post("/{profile_id}/apply-fix",
                      summary="Apply an accepted fix (cleans the return output, refused if signed off)")
async def apply_fix(
    profile_id: uuid.UUID,
    body: ApplyFixRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _engine(session).apply_fix(profile_id, field=body.field, transform=body.transform)


@profiles_router.get("/{profile_id}/suggest-defaults",
                     summary="Intelligent per-field default suggestions (AI + rule fallback)")
async def suggest_defaults(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await _engine(session).suggest_defaults(profile_id)


class ApplyDefaultsPick(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    field: str
    value: str


class ApplyDefaultsRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    picks: list[ApplyDefaultsPick]


@profiles_router.post("/{profile_id}/apply-defaults",
                      summary="Apply accepted default suggestions in one call (refused if signed off)")
async def apply_defaults(
    profile_id: uuid.UUID,
    body: ApplyDefaultsRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _engine(session).apply_defaults(
        profile_id, [{"field": p.field, "value": p.value} for p in body.picks],
    )


class SuppressRuleRequest(BaseModel):
    """Suppress a validation rule with an audit trail. `reason` is required — the sign-off will
    show these to whoever attests to the return, so an anonymous mute is not allowed."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    rule_key: str
    reason: str
    scope: str = "profile"    # 'profile' | 'pack'


@profiles_router.post("/{profile_id}/suppress-rule",
                      summary="Suppress a cross-field/format rule for this profile or for the whole pack")
async def suppress_rule(
    profile_id: uuid.UUID,
    body: SuppressRuleRequest,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("admin.configure")),
) -> dict:
    return await _engine(session).suppress_rule(
        profile_id,
        rule_key=body.rule_key, reason=body.reason, scope=body.scope,
        user_id=principal.user_id, user_name=principal.email,
    )


class RemoveSuppressionRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    rule_key: str
    scope: str = "profile"


@profiles_router.post("/{profile_id}/remove-suppression",
                      summary="Undo a rule suppression (unsuppresses at profile or pack scope)")
async def remove_suppression(
    profile_id: uuid.UUID,
    body: RemoveSuppressionRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _engine(session).remove_suppression(
        profile_id, rule_key=body.rule_key, scope=body.scope,
    )


class PreviewTransformRequest(BaseModel):
    """Ask 'what does this pipe produce over the profile's own cohort?' before saving a mapping."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    source_expression: str
    transform: str | None = None


def _json_safe(v):
    """Dates/datetimes aren't natively JSON serialisable; everything else passes through."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


@profiles_router.post(
    "/{profile_id}/preview-transform",
    summary="Dry-run a source+transform over the profile's cohort (first 20 records)",
)
async def preview_transform(
    profile_id: uuid.UUID,
    body: PreviewTransformRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    """Feed the Add/Edit-field dialog: show the user the input value and produced output for the
    first 20 records of *this* profile's cohort, plus distinct input/output lists. Uses exactly
    the same resolver + transform pipeline the validation/generate step uses so what you preview
    is what the return will ship. Per-row errors are caught so one bad record doesn't kill the
    preview."""
    from app.core.errors import WorkflowError
    from app.modules.exports.statutory import (
        _validate_transform_chain, apply_chain, resolve,
    )

    eng = _engine(session)
    await eng.get_profile(profile_id)     # 404 if the profile doesn't exist

    try:
        _validate_transform_chain(body.transform)
    except WorkflowError as e:
        # Deliberately 400 here (not 422): the dialog is asking "is this pipe usable?" and expects
        # a plain rejection, not the standard error envelope used by full mutations.
        raise HTTPException(status_code=400, detail=str(e))

    records = await eng.build_records()
    sample = records[:20]

    rows: list[dict] = []
    input_seen: list = []
    output_seen: list = []

    def _dedupe(seen: list, value) -> None:
        key = None if value is None else str(value)
        for existing in seen:
            existing_key = None if existing is None else str(existing)
            if existing_key == key:
                return
        seen.append(value)

    for rec in sample:
        raw = resolve(rec, body.source_expression) if body.source_expression else None
        try:
            produced = apply_chain(body.transform, raw)
            output = "" if produced is None else str(produced)
        except Exception as e:  # noqa: BLE001 — one bad row must not kill the preview
            msg = str(e).splitlines()[0][:160] if str(e) else e.__class__.__name__
            output = f"!!{msg}"
        rows.append({
            "studentRef": rec["student"]["ref"],
            "input": _json_safe(raw),
            "output": output,
        })
        _dedupe(input_seen, _json_safe(raw))
        _dedupe(output_seen, output)

    return {
        "sampled": len(sample),
        "totalRecords": len(records),
        "rows": rows,
        "distinct": {"inputs": input_seen, "outputs": output_seen},
        "error": None,
    }


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


# --- ICR G5 — statutory advisory ingestion (ingest → recommend → Registry accepts) ---

advisories_router = APIRouter(prefix="/report-advisories", tags=["exports"])


def _advisory_out(advisory) -> dict:
    from app.modules.exports.schemas import AdvisoryOut

    out = AdvisoryOut.model_validate(advisory).model_dump(by_alias=True)
    # Echo transient parse warnings when the service attached them (freshly ingested only).
    warnings = getattr(advisory, "parse_warnings", None)
    if warnings is not None:
        out["parseWarnings"] = warnings
    return out


@advisories_router.get("", summary="Ingested statutory advisories")
async def list_advisories(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    from app.modules.exports.advisory_service import AdvisoryService

    advisories = await AdvisoryService(session).list_recent()
    return {"advisories": [_advisory_out(a) for a in advisories]}


@advisories_router.post("/ingest", status_code=201,
                        summary="Ingest a published advisory and diff it against the current pack")
async def ingest_advisory(
    body: AdvisoryIngestRequest,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("admin.configure")),
) -> dict:
    from app.modules.exports.advisory_service import AdvisoryService

    advisory = await AdvisoryService(session).ingest(
        pack_code=body.pack_code, academic_year=body.academic_year, title=body.title,
        raw_text=body.raw_text, source=body.source, created_by=principal.user_id,
    )
    return _advisory_out(advisory)


# --- Assisted ingest: fetch/upload a published HESA doc, AI-draft it, then the same review flow ---

class AdvisoryUrlIngest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    pack_code: str = "HESA_STUDENT"
    academic_year: str | None = None
    title: str | None = None
    url: str


@advisories_router.post("/ingest-from-url", status_code=201,
                        summary="Fetch a published advisory from a URL, AI-draft the changes, and diff it")
async def ingest_from_url(
    body: AdvisoryUrlIngest,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("admin.configure")),
) -> dict:
    from app.core.errors import ValidationAppError
    from app.modules.exports.advisory_service import AdvisoryService
    from app.modules.exports.advisory_source import extract_text, fetch_url

    data, content_type = await fetch_url(body.url)
    text = extract_text(data, content_type=content_type, filename=body.url)
    if not text.strip():
        raise ValidationAppError("No readable text was found at that URL")
    advisory = await AdvisoryService(session).ingest(
        pack_code=body.pack_code, academic_year=body.academic_year,
        title=body.title or f"From {body.url[:80]}", raw_text=text, source="url",
        created_by=principal.user_id,
    )
    return _advisory_out(advisory)


@advisories_router.post("/ingest-upload", status_code=201,
                        summary="Upload a published advisory (PDF/notice), AI-draft the changes, and diff it")
async def ingest_upload(
    packCode: str = Form("HESA_STUDENT"),
    academicYear: str | None = Form(None),
    title: str | None = Form(None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("admin.configure")),
) -> dict:
    from app.core.config import get_settings
    from app.core.errors import ValidationAppError
    from app.modules.exports.advisory_service import AdvisoryService
    from app.modules.exports.advisory_source import extract_text

    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ValidationAppError(f"File is larger than the {get_settings().max_upload_mb} MB limit")
    text = extract_text(data, content_type=file.content_type or "", filename=file.filename or "")
    if not text.strip():
        raise ValidationAppError("Could not read any text from that file")
    advisory = await AdvisoryService(session).ingest(
        pack_code=packCode, academic_year=academicYear,
        title=title or f"From {file.filename or 'upload'}", raw_text=text, source="upload",
        created_by=principal.user_id,
    )
    return _advisory_out(advisory)


@advisories_router.get("/{advisory_id}", summary="One advisory with its proposed changes")
async def get_advisory(
    advisory_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    from app.modules.exports.advisory_service import AdvisoryService

    return _advisory_out(await AdvisoryService(session).get(advisory_id))


@advisories_router.post("/{advisory_id}/accept",
                        summary="Accept an advisory — makes its proposed pack the active version")
async def accept_advisory(
    advisory_id: uuid.UUID,
    body: AdvisoryDecision,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("reports.signoff")),
) -> dict:
    from app.modules.exports.advisory_service import AdvisoryService
    from app.modules.exports.schemas import SpecVersionOut

    version = await AdvisoryService(session).accept(
        advisory_id, user_id=principal.user_id, note=body.note,
    )
    out = SpecVersionOut.model_validate(version).model_dump(by_alias=True)
    out["fieldCount"] = len(version.fields or [])
    return out


@advisories_router.post("/{advisory_id}/reject", summary="Reject an advisory (no change to the pack)")
async def reject_advisory(
    advisory_id: uuid.UUID,
    body: AdvisoryDecision,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("reports.signoff")),
) -> dict:
    from app.modules.exports.advisory_service import AdvisoryService

    advisory = await AdvisoryService(session).reject(
        advisory_id, user_id=principal.user_id, note=body.note,
    )
    return _advisory_out(advisory)
