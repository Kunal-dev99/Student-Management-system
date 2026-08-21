"""Person Pydantic contracts (arch §11 — camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

from app.modules.person.constants import PersonRelationshipType


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class PersonCreate(_CamelModel):
    given_name: str = Field(min_length=1, max_length=150)
    family_name: str = Field(min_length=1, max_length=150)
    preferred_name: str | None = None
    email: EmailStr | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    external_person_ref: str | None = None


class PersonUpdate(_CamelModel):
    given_name: str | None = Field(default=None, min_length=1, max_length=150)
    family_name: str | None = Field(default=None, min_length=1, max_length=150)
    preferred_name: str | None = None
    email: EmailStr | None = None
    date_of_birth: date | None = None
    nationality: str | None = None


class RelationshipOut(_CamelModel):
    id: uuid.UUID
    relationship_type: PersonRelationshipType
    valid_from: date
    valid_to: date | None = None
    source_system: str | None = None


class PersonOut(_CamelModel):
    id: uuid.UUID
    external_person_ref: str | None = None
    given_name: str
    family_name: str
    preferred_name: str | None = None
    email: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    created_at: datetime
    updated_at: datetime
    relationships: list[RelationshipOut] = Field(default_factory=list)


class TimelineEntry(_CamelModel):
    kind: str            # e.g. "relationship"
    label: str           # human-readable summary
    at: date             # sort key
    detail: dict = Field(default_factory=dict)


class TimelineOut(_CamelModel):
    person_id: uuid.UUID
    entries: list[TimelineEntry]
