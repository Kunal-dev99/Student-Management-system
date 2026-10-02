"""Units of assessment (effective dating, Phase 9).

- ``/units-of-assessment``: the institution's UOA list (e.g. REF UOA 1 "Clinical Medicine").
- ``/persons/{id}/uoa``: a person's (supervisor's / staff member's) dated UOA. One change applies
  to every student they supervise, and a change recorded after a return was signed off is listed
  against those students as a retrospective change.
- A student's own UOA is a dated fact on ``/students/{id}/facts/uoa``.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import ConflictError, NotFoundError
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.person.models import Person
from app.modules.student_record.fact_history import PersonUoaHistoryService, today
from app.modules.student_record.models import UnitOfAssessment
from app.modules.student_record.periods import assert_backdate_allowed

uoa_router = APIRouter(prefix="/units-of-assessment", tags=["student"])
person_uoa_router = APIRouter(prefix="/persons", tags=["student"])


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UoaCreate(_Camel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    panel: str | None = Field(None, max_length=20)


class UoaUpdate(_Camel):
    name: str | None = Field(None, min_length=1, max_length=200)
    panel: str | None = Field(None, max_length=20)
    is_active: bool | None = None


class PersonUoaChange(_Camel):
    uoa_id: uuid.UUID
    effective_date: date | None = None
    reason: str | None = None


def uoa_out(u: UnitOfAssessment) -> dict:
    return {"id": str(u.id), "code": u.code, "name": u.name, "panel": u.panel, "isActive": u.is_active}


@uoa_router.get("", summary="Units of assessment")
async def list_uoas(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[dict]:
    rows = (await session.execute(select(UnitOfAssessment).order_by(UnitOfAssessment.code))).scalars().all()
    return [uoa_out(u) for u in rows]


@uoa_router.post("", status_code=201, summary="Add a unit of assessment")
async def create_uoa(
    body: UoaCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    code = body.code.strip()
    if (await session.execute(select(UnitOfAssessment).where(UnitOfAssessment.code == code))).scalar_one_or_none():
        raise ConflictError(f"A unit of assessment with code '{code}' already exists")
    u = UnitOfAssessment(code=code, name=body.name.strip(), panel=(body.panel or "").strip() or None)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return uoa_out(u)


@uoa_router.patch("/{uoa_id}", summary="Rename or retire a unit of assessment")
async def update_uoa(
    uoa_id: uuid.UUID,
    body: UoaUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    u = await session.get(UnitOfAssessment, uoa_id)
    if u is None:
        raise NotFoundError("Unit of assessment not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(u, k, v.strip() if isinstance(v, str) else v)
    await session.commit()
    await session.refresh(u)
    return uoa_out(u)


@person_uoa_router.get("/{person_id}/uoa", summary="A person's unit of assessment over time")
async def person_uoa_history(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.read")),
) -> dict:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError("Person not found")
    svc = PersonUoaHistoryService(session)
    names = {u.id: u for u in (await session.execute(select(UnitOfAssessment))).scalars().all()}

    def _label(uid):
        u = names.get(uid)
        return f"{u.code} {u.name}" if u else None

    rows = [svc.out(r) | {"uoa": _label(r.uoa_id)} for r in await svc.live_rows(person_id)]
    return {"personId": str(person_id), "currentUoaId": str(person.uoa_id) if person.uoa_id else None,
            "current": _label(person.uoa_id), "periods": rows}


@person_uoa_router.post("/{person_id}/uoa", summary="Record a person's unit of assessment from a date")
async def change_person_uoa(
    person_id: uuid.UUID,
    body: PersonUoaChange,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("person.write")),
) -> dict:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError("Person not found")
    on = body.effective_date or today()
    # A supervisor's UOA feeds their students' returns, so a date inside a signed-off return is an
    # amendment (the same rule as student facts).
    await assert_backdate_allowed(session, on, principal, what="This unit of assessment change")
    svc = PersonUoaHistoryService(session)
    row = await svc.change(person, await svc.normalise(body.uoa_id), effective_from=on,
                           reason=(body.reason or "").strip() or None, user_id=principal.user_id)
    await session.commit()
    return {"row": svc.out(row), "currentUoaId": str(person.uoa_id) if person.uoa_id else None}
