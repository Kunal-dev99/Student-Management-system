"""Person and identity ORM models (arch §8.3).

The central object is the person, tracked across every identity it holds over time.
Portable across SQLite/PostgreSQL (D-04): Enum renders as VARCHAR+CHECK on SQLite.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.person.constants import PersonContactChannel, PersonRelationshipType


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

    # F2 — set when the person has been pseudonymised via GDPR erasure. Presence is a hard read
    # signal for the notifier and everywhere else: never contact, never surface identifying info.
    pseudonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    relationships: Mapped[list["PersonRelationship"]] = relationship(
        back_populates="person", lazy="selectin", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["PersonContact"]] = relationship(
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


# --- F2 — contacts + merge record --------------------------------------------

class PersonContact(UUIDMixin, TimestampMixin, Base):
    """A way to reach a person other than the primary email on Person.

    The notifier must honour do_not_contact; nothing else in the platform may bypass it.
    """
    __tablename__ = "person_contact"

    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[PersonContactChannel] = mapped_column(
        Enum(PersonContactChannel, name="person_contact_channel")
    )
    value: Mapped[str] = mapped_column(String(320))
    label: Mapped[str | None] = mapped_column(String(60), nullable=True)  # "work", "next of kin"
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)

    person: Mapped[Person] = relationship(back_populates="contacts")


class PersonMergeRecord(UUIDMixin, Base):
    """Immutable evidence of a merge — the losing person's row is gone, this stays.

    ``fk_touched`` records every (table, column, rows_updated) tuple that the merge rewrote,
    so a later reviewer can reconstruct exactly what was joined.
    """
    __tablename__ = "person_merge_record"

    surviving_person_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    losing_person_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    losing_person_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fk_touched: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
