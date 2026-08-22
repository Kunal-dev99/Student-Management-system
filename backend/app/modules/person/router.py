"""Person HTTP endpoints (arch §11.5 — person)."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.pagination import PageParams, list_envelope, page_params
from app.db.session import get_session
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.repository import PersonRepository
from app.modules.person.schemas import (
    PersonCreate,
    PersonOut,
    PersonUpdate,
    RelationshipOut,
    TimelineOut,
)
from app.modules.person.service import PersonService

router = APIRouter(prefix="/persons", tags=["person"])


class _RelCamel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


def _service(session: AsyncSession) -> PersonService:
    return PersonService(PersonRepository(session))


@router.get("", summary="List persons")
async def list_persons(
    page: PageParams = Depends(page_params),
    search: str | None = Query(None, description="match name or email"),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.read")),
) -> dict:
    rows, total = await _service(session).list_persons(
        limit=page.limit, offset=page.offset, search=search
    )
    data = [PersonOut.model_validate(p).model_dump(by_alias=True) for p in rows]
    return list_envelope(data, limit=page.limit, total=total)


@router.post("", response_model=PersonOut, status_code=201, summary="Create a person")
async def create_person(
    body: PersonCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.write")),
) -> PersonOut:
    person = await _service(session).create_person(body)
    return PersonOut.model_validate(person)


@router.get("/{person_id}", response_model=PersonOut, summary="Get a person")
async def get_person(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.read")),
) -> PersonOut:
    person = await _service(session).get_person(person_id)
    return PersonOut.model_validate(person)


@router.patch("/{person_id}", response_model=PersonOut, summary="Update a person")
async def update_person(
    person_id: uuid.UUID,
    body: PersonUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.write")),
) -> PersonOut:
    person = await _service(session).update_person(person_id, body)
    return PersonOut.model_validate(person)


@router.get(
    "/{person_id}/relationships",
    response_model=list[RelationshipOut],
    summary="Identities held over time",
)
async def person_relationships(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.read")),
) -> list[RelationshipOut]:
    person = await _service(session).get_person(person_id)
    return [RelationshipOut.model_validate(r) for r in person.relationships]


# --- Phase 6.4 — person ↔ employee/researcher continuity (CIO vision GAP-04) ---

class RelationshipRequest(_RelCamel):
    relationship_type: PersonRelationshipType
    valid_from: date | None = None
    source_system: str | None = None


@router.post("/{person_id}/relationships", status_code=201,
             summary="Open a relationship (e.g. a PGR becomes an employee) — keeps one person_id")
async def open_relationship(
    person_id: uuid.UUID,
    body: RelationshipRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.write")),
) -> dict:
    """Opens a NEW relationship without closing existing ones, so a student can be an employee at
    the same time. History is preserved: nothing is overwritten (arch §8.3)."""
    svc = PersonService(PersonRepository(session))
    await svc.transition_identity(
        person_id, end_type=None, open_type=body.relationship_type,
        source_system=body.source_system, on_date=body.valid_from,
    )
    await session.commit()
    return await _relationships_payload(svc, person_id)


@router.post("/{person_id}/relationships/{relationship_type}/close",
             summary="Close a current relationship (e.g. employment ended)")
async def close_relationship(
    person_id: uuid.UUID,
    relationship_type: PersonRelationshipType,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.write")),
) -> dict:
    svc = PersonService(PersonRepository(session))
    await svc.transition_identity(person_id, end_type=relationship_type, open_type=None)
    await session.commit()
    return await _relationships_payload(svc, person_id)


async def _relationships_payload(svc: PersonService, person_id: uuid.UUID) -> dict:
    person = await svc.get_person(person_id)
    rels = [
        {
            "relationshipType": r.relationship_type.value,
            "validFrom": r.valid_from.isoformat(),
            "validTo": r.valid_to.isoformat() if r.valid_to else None,
            "sourceSystem": r.source_system,
            "current": r.valid_to is None,
        }
        for r in sorted(person.relationships, key=lambda r: r.valid_from)
    ]
    return {
        "personId": str(person_id),
        "relationships": rels,
        "currentTypes": sorted({r["relationshipType"] for r in rels if r["current"]}),
    }


@router.get("/{person_id}/timeline", response_model=TimelineOut, summary="Full lifecycle")
async def person_timeline(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("person.read")),
) -> TimelineOut:
    entries = await _service(session).timeline(person_id)
    return TimelineOut(person_id=person_id, entries=entries)
