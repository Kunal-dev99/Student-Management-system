"""Admin-defined custom student attributes — service layer.

Captures an attribute a statutory return needs but the core model doesn't hold. A definition is
requested (with mandatory commentary), decided by someone other than the requester, activated, and
only then takes a value per student. Statutory mappings read these through the ``custom.<key>``
source path (wired in ``exports.statutory.build_records`` and the record-schema catalog).

Governance (custom attribute plan, Phase 1): request → approve | reject → activate. Every
transition is written to ``student_custom_field_event`` and to the audit log. Only *live*
attributes (active, or active-but-under-review) take values, are offered for mapping and are read
by a return; a pending or rejected request is invisible to all three.

Effective dating, Phase 6: an attribute can opt in to dated history (``track_history``). Its values
are then recorded with the date they took effect, the return reads the value as at the period it
reports, and switching history on is one-way so the audit trail can't be dropped.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.errors import (
    ConflictError, NotFoundError, PermissionError, ValidationAppError, WorkflowError,
)
from app.core.principal import Principal
from app.modules.person.models import Person
from app.modules.student_record.models import (
    Student,
    StudentCustomField,
    StudentCustomFieldAssessment,
    StudentCustomFieldEvent,
    StudentCustomValue,
)

log = logging.getLogger("pgr.custom_attributes")

_ALLOWED_TYPES = {"string", "number", "date", "code"}
_KEY_RE = re.compile(r"[^a-z0-9]+")


class Status:
    """Lifecycle of a custom attribute (plan §5). Stored as plain strings."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    REVIEW = "review"
    RETIRED = "retired"

    ALL = (PENDING, APPROVED, REJECTED, ACTIVE, REVIEW, RETIRED)
    # Live = takes values, mappable, read by a return. "review" is still live: an attribute being
    # reviewed for retirement keeps working until it is actually retired.
    LIVE = (ACTIVE, REVIEW)


def slugify(label: str) -> str:
    """A stable machine key from a human label, e.g. 'Disability (detail)' -> 'disability_detail'."""
    key = _KEY_RE.sub("_", (label or "").strip().lower()).strip("_")
    return key[:60] or "field"


def is_live(field: StudentCustomField) -> bool:
    return field.status in Status.LIVE


class CustomFieldService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_fields(self, statuses: tuple[str, ...] | None = None) -> list[StudentCustomField]:
        q = select(StudentCustomField).order_by(StudentCustomField.label)
        if statuses:
            bad = set(statuses) - set(Status.ALL)
            if bad:
                raise ValidationAppError(f"Unknown status: {', '.join(sorted(bad))}. "
                                         f"Use one of {', '.join(Status.ALL)}.")
            q = q.where(StudentCustomField.status.in_(statuses))
        return list((await self.session.execute(q)).scalars().all())

    async def get_field(self, field_id: uuid.UUID, *, for_update: bool = False) -> StudentCustomField:
        q = select(StudentCustomField).where(StudentCustomField.id == field_id)
        if for_update:
            # Two checkers deciding the same request at once: the second waits, then sees the
            # first decision and is refused by the state check.
            q = q.with_for_update()
        f = (await self.session.execute(q)).scalar_one_or_none()
        if f is None:
            raise NotFoundError("Custom attribute not found")
        return f

    async def live_field(self, field_id: uuid.UUID) -> StudentCustomField:
        """The attribute, refused unless it is live — the gate for entering values."""
        field = await self.get_field(field_id)
        if not is_live(field):
            raise WorkflowError(
                f"'{field.label}' is {field.status}, not active — values can only be entered for an "
                "active attribute."
            )
        return field

    # --- governance ---------------------------------------------------------------------------

    async def request_field(
        self, *, label: str, data_type: str, reason: str, principal: Principal,
        track_history: bool = False,
    ) -> StudentCustomField:
        """The maker's step: a pending request. Nothing is mappable or enterable until a
        different person approves it and it is activated."""
        label = (label or "").strip()
        reason = (reason or "").strip()
        if not label:
            raise ValidationAppError("A label is required.")
        if len(label) > 120:
            raise ValidationAppError("The label must be 120 characters or fewer.")
        if not reason:
            raise ValidationAppError("A reason is required — say why this attribute is being captured.")
        data_type = (data_type or "string").strip().lower()
        if data_type not in _ALLOWED_TYPES:
            raise ValidationAppError(f"Type must be one of {', '.join(sorted(_ALLOWED_TYPES))}.")
        key = slugify(label)
        exists = (await self.session.execute(
            select(StudentCustomField).where(StudentCustomField.key == key)
        )).scalar_one_or_none()
        if exists is not None:
            raise ConflictError(
                f"A custom attribute with key '{key}' already exists ('{exists.label}', {exists.status})."
            )
        field = StudentCustomField(
            key=key, label=label, data_type=data_type, reason=reason,
            created_by_user_id=principal.user_id, track_history=bool(track_history),
            status=Status.PENDING,
        )
        self.session.add(field)
        await self.session.flush()
        await self._event(field, "requested", None, Status.PENDING, principal, reason,
                          detail={"dataType": data_type, "trackHistory": bool(track_history)})
        # Assess straight away so the approver sees it. The check is advisory: if it fails the
        # request still stands (the savepoint keeps a failed check from poisoning the
        # transaction), and it can be re-run from the queue.
        try:
            async with self.session.begin_nested():
                await self._assess(field, principal)
        except Exception:                       # noqa: BLE001 — advisory step, logged
            log.exception("Assessment of requested attribute %s failed", field.key)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def approve(
        self, field_id: uuid.UUID, *, principal: Principal, reason: str | None = None,
        activate: bool = False,
    ) -> StudentCustomField:
        """The checker's step. Refused for the requester (maker-checker). ``activate`` makes it
        live in the same call — two recorded transitions, approve then activate."""
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.PENDING, "approve")
        self._refuse_self_decision(field, principal)
        latest = (await self.latest_assessments([field.id])).get(field.id)
        if latest is None:
            latest = await self._assess(field, principal)
        if latest.verdict == "duplicate" and not (reason or "").strip():
            raise ValidationAppError(
                f"'{field.label}' looks like a duplicate ({'; '.join(latest.result.get('flags', [])[:2])}). "
                "Give a reason to approve it anyway."
            )
        field.status = Status.APPROVED
        self._stamp_decision(field, principal, reason)
        await self._event(field, "approved", Status.PENDING, Status.APPROVED, principal, field.decision_reason)
        if activate:
            field.status = Status.ACTIVE
            await self._event(field, "activated", Status.APPROVED, Status.ACTIVE, principal, None)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def reject(self, field_id: uuid.UUID, *, principal: Principal, reason: str) -> StudentCustomField:
        reason = (reason or "").strip()
        if not reason:
            raise ValidationAppError("A reason is required to reject a request.")
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.PENDING, "reject")
        self._refuse_self_decision(field, principal)
        field.status = Status.REJECTED
        self._stamp_decision(field, principal, reason)
        await self._event(field, "rejected", Status.PENDING, Status.REJECTED, principal, reason)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def activate(self, field_id: uuid.UUID, *, principal: Principal) -> StudentCustomField:
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.APPROVED, "activate")
        field.status = Status.ACTIVE
        await self._event(field, "activated", Status.APPROVED, Status.ACTIVE, principal, None)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def withdraw(self, field_id: uuid.UUID, *, principal: Principal) -> None:
        """Remove a pending request (raised by mistake, or no longer wanted). Nothing was ever
        entered against it. Decided attributes are kept: a rejection is part of the record, and
        an active attribute holds student data."""
        field = await self.get_field(field_id, for_update=True)
        if field.status != Status.PENDING:
            raise ConflictError(
                f"'{field.label}' is {field.status}; only a pending request can be withdrawn. "
                "Attributes that have been decided are kept for the record."
            )
        await self._event(field, "withdrawn", Status.PENDING, None, principal, None)
        await self.session.delete(field)
        await self.session.commit()

    # --- lifecycle after activation (Phase 3) ---------------------------------------------------
    # active -> review -> retired, review -> active (keep), retired -> active (restore). Retiring
    # takes the attribute out of every live path (values, mapping, the return) and deletes
    # nothing: its values and dated history stay, readable, and come back on restore.

    async def start_review(self, field_id: uuid.UUID, *, principal: Principal | None, reason: str,
                           system: bool = False) -> StudentCustomField:
        reason = (reason or "").strip()
        if not reason:
            raise ValidationAppError("Say why this attribute should be reviewed.")
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.ACTIVE, "put under review")
        field.status = Status.REVIEW
        await self._event(field, "review_started", Status.ACTIVE, Status.REVIEW, principal, reason,
                          detail={"system": True} if system else None)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def keep(self, field_id: uuid.UUID, *, principal: Principal, reason: str | None = None) -> StudentCustomField:
        """End a review without retiring: the attribute is still needed."""
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.REVIEW, "keep")
        field.status = Status.ACTIVE
        await self._event(field, "kept", Status.REVIEW, Status.ACTIVE, principal, (reason or "").strip() or None)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def retire(self, field_id: uuid.UUID, *, principal: Principal, reason: str) -> StudentCustomField:
        reason = (reason or "").strip()
        if not reason:
            raise ValidationAppError("A reason is required to retire an attribute.")
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.REVIEW, "retire")
        # Whoever raised the review doesn't also close it by retiring. A system-raised review has
        # no person, so anyone with the approve right may retire it.
        started = (await self.session.execute(
            select(StudentCustomFieldEvent.actor_user_id)
            .where(StudentCustomFieldEvent.custom_field_id == field.id,
                   StudentCustomFieldEvent.action == "review_started")
            .order_by(StudentCustomFieldEvent.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if started is not None and started == principal.user_id:
            raise PermissionError("You put this attribute under review, so someone else must retire it.")
        live = [d for d in await self.dependencies(field) if d["blocksRetirement"]]
        if live:
            raise ConflictError(
                f"'{field.label}' is still mapped in "
                + ", ".join(f"{d['profileCode']} {d['academicYear']} ({d['targetField']})" for d in live)
                + ". Re-map or remove those fields first; signed-off returns are unaffected."
            )
        values = await self.value_count(field.id)
        field.status = Status.RETIRED
        await self._event(field, "retired", Status.REVIEW, Status.RETIRED, principal, reason,
                          detail={"valuesRetained": values})
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def restore(self, field_id: uuid.UUID, *, principal: Principal, reason: str) -> StudentCustomField:
        reason = (reason or "").strip()
        if not reason:
            raise ValidationAppError("A reason is required to restore an attribute.")
        field = await self.get_field(field_id, for_update=True)
        self._require_status(field, Status.RETIRED, "restore")
        field.status = Status.ACTIVE
        await self._event(field, "restored", Status.RETIRED, Status.ACTIVE, principal, reason,
                          detail={"valuesRetained": await self.value_count(field.id)})
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def dependencies(self, field: StudentCustomField) -> list[dict]:
        """Every report-profile field mapped to this attribute. A mapping in an active profile
        that isn't signed off blocks retirement (it would silently start reading blank); a
        signed-off return is a frozen snapshot and doesn't."""
        from app.modules.exports.models import ReportFieldMapping, ReportProfile

        rows = (await self.session.execute(
            select(ReportFieldMapping, ReportProfile)
            .join(ReportProfile, ReportProfile.id == ReportFieldMapping.profile_id)
            .where(ReportFieldMapping.source_expression == f"custom.{field.key}")
            .order_by(ReportProfile.academic_year.desc(), ReportProfile.code)
        )).all()
        return [{
            "profileId": str(p.id), "profileCode": p.code, "profileName": p.name,
            "academicYear": p.academic_year, "profileActive": bool(p.is_active),
            "signedOff": p.signed_off_at is not None,
            "mappingId": str(m.id), "targetField": m.target_field, "required": bool(m.required),
            "blocksRetirement": bool(p.is_active) and p.signed_off_at is None,
        } for m, p in rows]

    async def value_count(self, field_id: uuid.UUID) -> int:
        from sqlalchemy import func

        return int((await self.session.execute(
            select(func.count()).select_from(StudentCustomValue)
            .where(StudentCustomValue.custom_field_id == field_id,
                   StudentCustomValue.value.is_not(None), StudentCustomValue.value != "")
        )).scalar_one())

    async def usage(self, fields) -> dict:
        """Per attribute: filled values, last value change, and how many profile fields map it.
        Three grouped queries for the whole catalogue, no per-row lookups."""
        from sqlalchemy import func

        from app.modules.exports.models import ReportFieldMapping

        fields = list(fields)
        ids = [f.id for f in fields]
        if not ids:
            return {}
        filled = dict((await self.session.execute(
            select(StudentCustomValue.custom_field_id, func.count())
            .where(StudentCustomValue.custom_field_id.in_(ids),
                   StudentCustomValue.value.is_not(None), StudentCustomValue.value != "")
            .group_by(StudentCustomValue.custom_field_id)
        )).all())
        updated = dict((await self.session.execute(
            select(StudentCustomValue.custom_field_id, func.max(StudentCustomValue.updated_at))
            .where(StudentCustomValue.custom_field_id.in_(ids))
            .group_by(StudentCustomValue.custom_field_id)
        )).all())
        by_path = dict((await self.session.execute(
            select(ReportFieldMapping.source_expression, func.count())
            .where(ReportFieldMapping.source_expression.in_([f"custom.{f.key}" for f in fields]))
            .group_by(ReportFieldMapping.source_expression)
        )).all())
        return {f.id: {
            "valueCount": int(filled.get(f.id, 0)),
            "lastValueUpdate": updated[f.id].isoformat() if updated.get(f.id) else None,
            "mappingCount": int(by_path.get(f"custom.{f.key}", 0)),
        } for f in fields}

    async def events(self, field_id: uuid.UUID | None = None, *, limit: int = 200) -> list[StudentCustomFieldEvent]:
        q = select(StudentCustomFieldEvent).order_by(StudentCustomFieldEvent.created_at.desc()).limit(limit)
        if field_id is not None:
            q = q.where(StudentCustomFieldEvent.custom_field_id == field_id)
        return list((await self.session.execute(q)).scalars().all())

    # --- assessment (Phase 2) ------------------------------------------------------------------

    async def assess(self, field_id: uuid.UUID, *, principal: Principal) -> StudentCustomFieldAssessment:
        """Re-run the necessity check (e.g. after a new spec version was accepted)."""
        field = await self.get_field(field_id)
        row = await self._assess(field, principal)
        await self.session.commit()
        return row

    async def preview_assessment(self, *, label: str, reason: str, data_type: str | None) -> dict:
        """The same check for a request not yet raised — drives the warning in the request form."""
        from app.modules.student_record.custom_attr_assessment import assess

        return await assess(self.session, label=label, reason=reason, data_type=data_type)

    async def latest_assessments(self, field_ids) -> dict:
        ids = list(field_ids)
        if not ids:
            return {}
        rows = (await self.session.execute(
            select(StudentCustomFieldAssessment)
            .where(StudentCustomFieldAssessment.custom_field_id.in_(ids))
            .order_by(StudentCustomFieldAssessment.created_at)
        )).scalars().all()
        return {r.custom_field_id: r for r in rows}     # later rows overwrite earlier ones

    async def _assess(self, field: StudentCustomField, principal: Principal | None) -> StudentCustomFieldAssessment:
        from app.modules.student_record.custom_attr_assessment import assess

        result = await assess(self.session, label=field.label, reason=field.reason,
                              data_type=field.data_type, exclude_field_id=field.id)
        row = StudentCustomFieldAssessment(
            custom_field_id=field.id, verdict=result["verdict"],
            specification=result["hesa"]["specification"], result=result,
            assessed_by_user_id=principal.user_id if principal else None,
        )
        self.session.add(row)
        await self._event(field, "assessed", field.status, field.status, principal,
                          "; ".join(result["flags"]) or None,
                          detail={"verdict": result["verdict"], "specification": result["hesa"]["specification"]})
        await self.session.flush()
        return row

    @staticmethod
    def _require_status(field: StudentCustomField, expected: str, action: str) -> None:
        if field.status != expected:
            raise ConflictError(f"Can't {action} '{field.label}': it is {field.status}, not {expected}.")

    @staticmethod
    def _refuse_self_decision(field: StudentCustomField, principal: Principal) -> None:
        if field.created_by_user_id is not None and field.created_by_user_id == principal.user_id:
            raise PermissionError(
                "You requested this attribute, so someone else must decide on it (maker-checker)."
            )

    @staticmethod
    def _stamp_decision(field: StudentCustomField, principal: Principal, reason: str | None) -> None:
        field.decided_by_user_id = principal.user_id
        field.decided_at = datetime.now(timezone.utc)
        field.decision_reason = (reason or "").strip() or None

    async def _event(
        self, field: StudentCustomField, action: str, from_status: str | None, to_status: str | None,
        principal: Principal | None, notes: str | None, *, detail: dict | None = None,
    ) -> None:
        self.session.add(StudentCustomFieldEvent(
            custom_field_id=field.id, field_key=field.key, field_label=field.label, action=action,
            from_status=from_status, to_status=to_status,
            actor_user_id=principal.user_id if principal else None,
            actor_email=principal.email if principal else None,
            notes=notes, detail=detail,
        ))
        await record_audit(
            self.session, action=f"custom_attribute.{action}", entity_type="student_custom_field",
            entity_id=field.id, actor_user_id=principal.user_id if principal else None,
            actor_email=principal.email if principal else None,
            detail={"key": field.key, "label": field.label, "from": from_status, "to": to_status,
                    "notes": notes, **(detail or {})},
        )

    # --- values -------------------------------------------------------------------------------

    async def enable_history(self, field_id: uuid.UUID, *, user_id: uuid.UUID | None) -> StudentCustomField:
        """Start keeping dated history. Values already entered open their history from the
        student's start date, marked as rebuilt (origin ``backfill``). One-way: switching it off
        would drop the dates a return may already have used."""
        from app.modules.student_record.fact_history import CustomValueHistoryService

        field = await self.get_field(field_id)
        if field.track_history:
            return field
        field.track_history = True
        hist = CustomValueHistoryService(self.session)
        rows = (await self.session.execute(
            select(StudentCustomValue, Student.start_date)
            .join(Student, Student.id == StudentCustomValue.student_id)
            .where(StudentCustomValue.custom_field_id == field_id)
        )).all()
        for cv, start in rows:
            if cv.value not in (None, ""):
                await hist.initialise(cv, valid_from=start or cv.created_at.date(), origin="backfill",
                                      reason="Value entered before history was kept", user_id=user_id)
        await self.session.commit()
        await self.session.refresh(field)
        return field

    async def field_values(self, field_id: uuid.UUID) -> list[dict]:
        """Every student with their current value for this field (blank if unset) — drives the
        data-entry grid."""
        field = await self.get_field(field_id)
        if field.status not in (*Status.LIVE, Status.RETIRED):
            raise WorkflowError(f"'{field.label}' is {field.status}; it has no values yet.")
        existing = {
            v.student_id: v.value
            for v in (await self.session.execute(
                select(StudentCustomValue).where(StudentCustomValue.custom_field_id == field_id)
            )).scalars().all()
        }
        rows = (await self.session.execute(
            select(Student, Person).join(Person, Person.id == Student.person_id)
            .order_by(Student.student_ref)
        )).all()
        return [
            {
                "studentId": str(s.id),
                "studentRef": s.student_ref,
                "studentName": f"{p.given_name} {p.family_name}",
                "value": existing.get(s.id),
            }
            for s, p in rows
        ]

    async def set_values(
        self, field_id: uuid.UUID, *, entries: list[dict], user_id: uuid.UUID | None,
        effective_date: date | None = None,
    ) -> int:
        """Upsert values for the given students. A blank/None value clears the row. Returns the
        number of students with a non-empty value after the write.

        For an attribute that keeps history, each value is recorded from ``effective_date``
        (default today) instead of overwriting, and clearing is refused."""
        field = await self.live_field(field_id)
        if field.track_history:
            return await self._set_dated_values(field, entries, user_id, effective_date)
        current = {
            v.student_id: v
            for v in (await self.session.execute(
                select(StudentCustomValue).where(StudentCustomValue.custom_field_id == field_id)
            )).scalars().all()
        }
        filled: set[uuid.UUID] = {sid for sid, v in current.items() if v.value not in (None, "")}
        for e in entries or []:
            try:
                sid = uuid.UUID(str(e.get("studentId")))
            except (ValueError, TypeError):
                continue
            val = e.get("value")
            val = val.strip() if isinstance(val, str) else val
            row = current.get(sid)
            if val in (None, ""):
                if row is not None:
                    await self.session.delete(row)
                    current.pop(sid, None)
                filled.discard(sid)
                continue
            if row is None:
                self.session.add(StudentCustomValue(
                    custom_field_id=field_id, student_id=sid, value=val,
                    updated_by_user_id=user_id,
                ))
            else:
                row.value = val
                row.updated_by_user_id = user_id
            filled.add(sid)
        await self.session.commit()
        return len(filled)

    async def _set_dated_values(
        self, field: StudentCustomField, entries: list[dict], user_id: uuid.UUID | None,
        effective_date: date | None,
    ) -> int:
        from app.modules.student_record.fact_history import CustomValueHistoryService, today

        on = effective_date or today()
        hist = CustomValueHistoryService(self.session)
        current = {
            v.student_id: v
            for v in (await self.session.execute(
                select(StudentCustomValue).where(StudentCustomValue.custom_field_id == field.id)
            )).scalars().all()
        }
        for e in entries or []:
            try:
                sid = uuid.UUID(str(e.get("studentId")))
            except (ValueError, TypeError):
                continue
            val = e.get("value")
            val = val.strip() if isinstance(val, str) else val
            cv = current.get(sid)
            if val in (None, ""):
                if cv is not None and cv.value not in (None, ""):
                    raise WorkflowError(
                        f"'{field.label}' keeps dated history, so a value can't be cleared — "
                        "record the new value from the date it changed"
                    )
                continue
            student = await self.session.get(Student, sid)
            if student is None:
                continue
            if student.start_date is not None and on < student.start_date:
                raise WorkflowError(
                    f"{student.student_ref}: the value can't take effect before the student's start "
                    f"date ({student.start_date})"
                )
            if cv is None:
                cv = StudentCustomValue(custom_field_id=field.id, student_id=sid, value=None,
                                        updated_by_user_id=user_id)
                if getattr(student, "tenant_id", None) is not None:
                    cv.tenant_id = student.tenant_id
                self.session.add(cv)
                await self.session.flush()
                current[sid] = cv
            await hist.change(cv, str(val), effective_from=on, user_id=user_id)
            cv.updated_by_user_id = user_id
        await self.session.commit()
        return sum(1 for v in current.values() if v.value not in (None, ""))
