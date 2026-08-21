"""Person and identity ORM models (arch §8.3).

The central object is the person, tracked across every identity it holds over time.
Portable across SQLite/PostgreSQL (D-04): Enum renders as VARCHAR+CHECK on SQLite.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.person.constants import PersonRelationshipType


class Person(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "person"

    external_person_ref: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    given_name: Mapped[str] = mapped_column(String(150))
    family_name: Mapped[str] = mapped_column(String(150))
    preferred_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True, index=True)
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)

    relationships: Mapped[list["PersonRelationship"]] = relationship(
        back_populates="person", lazy="selectin", cascade="all, delete-orphan"
    )


class PersonRelationship(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "person_relationship"

    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[PersonRelationshipType] = mapped_column(
        Enum(PersonRelationshipType, name="person_relationship_type")
    )
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # null = current
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)

    person: Mapped[Person] = relationship(back_populates="relationships")
