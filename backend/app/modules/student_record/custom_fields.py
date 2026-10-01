"""Admin-defined custom student attributes — service layer.

Captures an attribute a statutory return needs but the core model doesn't hold. A definition is
created once (with mandatory commentary), then a value is entered per student. Statutory mappings
read these through the ``custom.<key>`` source path (wired in ``exports.statutory.build_records``
and the record-schema catalog).

Effective dating, Phase 6: an attribute can opt in to dated history (``track_history``). Its values
are then recorded with the date they took effect, the return reads the value as at the period it
reports, and switching history on is one-way so the audit trail can't be dropped.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError, WorkflowError
from app.modules.person.models import Person
from app.modules.student_record.models import (
    Student,
    StudentCustomField,
    StudentCustomValue,
)

_ALLOWED_TYPES = {"string", "number", "date", "code"}
_KEY_RE = re.compile(r"[^a-z0-9]+")


def slugify(label: str) -> str:
    """A stable machine key from a human label, e.g. 'Disability (detail)' -> 'disability_detail'."""
    key = _KEY_RE.sub("_", (label or "").strip().lower()).strip("_")
    return key[:60] or "field"


class CustomFieldService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_fields(self) -> list[StudentCustomField]:
        return list((await self.session.execute(
            select(StudentCustomField).order_by(StudentCustomField.label)
        )).scalars().all())

    async def get_field(self, field_id: uuid.UUID) -> StudentCustomField:
        f = (await self.session.execute(
            select(StudentCustomField).where(StudentCustomField.id == field_id)
        )).scalar_one_or_none()
        if f is None:
            raise NotFoundError("Custom field not found")
        return f

    async def create_field(
        self, *, label: str, data_type: str, reason: str, user_id: uuid.UUID | None,
        track_history: bool = False,
    ) -> StudentCustomField:
        label = (label or "").strip()
        reason = (reason or "").strip()
        if not label:
            raise ValidationAppError("A label is required.")
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
            raise ConflictError(f"A custom attribute with key '{key}' already exists.")
        field = StudentCustomField(
            key=key, label=label, data_type=data_type, reason=reason,
            created_by_user_id=user_id, track_history=bool(track_history),
        )
        self.session.add(field)
        await self.session.commit()
        await self.session.refresh(field)
        return field

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

    async def delete_field(self, field_id: uuid.UUID) -> None:
        field = await self.get_field(field_id)
        await self.session.delete(field)
        await self.session.commit()

    async def field_values(self, field_id: uuid.UUID) -> list[dict]:
        """Every student with their current value for this field (blank if unset) — drives the
        data-entry grid."""
        await self.get_field(field_id)
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
        field = await self.get_field(field_id)
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
