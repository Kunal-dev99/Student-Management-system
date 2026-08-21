"""Person business rules (arch §6.1, §8.3). Services own transactions."""
from __future__ import annotations

import uuid

from datetime import date

from app.core.errors import ConflictError, NotFoundError
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.person.repository import PersonRepository
from app.modules.person.schemas import (
    PersonCreate,
    PersonUpdate,
    TimelineEntry,
)


class PersonService:
    def __init__(self, repo: PersonRepository) -> None:
        self.repo = repo

    async def list_persons(self, *, limit: int, offset: int, search: str | None):
        return await self.repo.list(limit=limit, offset=offset, search=search)

    async def get_person(self, person_id: uuid.UUID) -> Person:
        person = await self.repo.get(person_id)
        if person is None:
            raise NotFoundError("Person not found")
        return person

    async def create_person(self, data: PersonCreate) -> Person:
        person = Person(
            given_name=data.given_name,
            family_name=data.family_name,
            preferred_name=data.preferred_name,
            email=data.email.lower() if data.email else None,
            date_of_birth=data.date_of_birth,
            nationality=data.nationality,
            external_person_ref=data.external_person_ref,
        )
        try:
            await self.repo.add(person)
            await self.repo.session.commit()
        except Exception as exc:  # unique email/ref clash
            await self.repo.session.rollback()
            raise ConflictError("A person with that email or reference already exists") from exc
        await self.repo.session.refresh(person)
        return person

    async def update_person(self, person_id: uuid.UUID, data: PersonUpdate) -> Person:
        person = await self.get_person(person_id)
        patch = data.model_dump(exclude_unset=True)
        if "email" in patch and patch["email"]:
            patch["email"] = patch["email"].lower()
        for key, value in patch.items():
            setattr(person, key, value)
        await self.repo.session.commit()
        await self.repo.session.refresh(person)
        return person

    async def transition_identity(
        self,
        person_id: uuid.UUID,
        *,
        end_type: PersonRelationshipType | None,
        open_type: PersonRelationshipType | None,
        source_system: str | None = None,
        on_date: date | None = None,
    ) -> None:
        """History-preserving identity change: close the current `end_type` relationship
        (set valid_to) and open a new `open_type` one (arch §8.6, §8.7 history rule).
        Caller commits."""
        person = await self.get_person(person_id)
        today = on_date or date.today()
        if end_type is not None:
            for rel in person.relationships:
                if rel.relationship_type == end_type and rel.valid_to is None:
                    rel.valid_to = today
        if open_type is not None:
            person.relationships.append(
                PersonRelationship(
                    relationship_type=open_type,
                    valid_from=today,
                    valid_to=None,
                    source_system=source_system,
                )
            )
        await self.repo.session.flush()

    async def timeline(self, person_id: uuid.UUID) -> list[TimelineEntry]:
        """Lifecycle across identities. Phase 1 sources person_relationship; later phases
        fold in applications, student record, funding, thesis, completion."""
        person = await self.get_person(person_id)
        entries: list[TimelineEntry] = []
        for rel in person.relationships:
            span = f"{rel.valid_from} to {rel.valid_to or 'current'}"
            entries.append(
                TimelineEntry(
                    kind="relationship",
                    label=f"{rel.relationship_type.value.title()} ({span})",
                    at=rel.valid_from,
                    detail={
                        "relationshipType": rel.relationship_type.value,
                        "validFrom": rel.valid_from.isoformat(),
                        "validTo": rel.valid_to.isoformat() if rel.valid_to else None,
                        "sourceSystem": rel.source_system,
                    },
                )
            )
        entries.sort(key=lambda e: e.at)
        return entries
