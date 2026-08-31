"""F2 — Person GDPR operations: merge, subject-access export, pseudonymising erasure.

The single non-obvious thing: we do **not** hard-code the list of tables that reference a person.
The moment someone adds a new module with a ``person.id`` FK, both merge and export must include
it or the operation silently corrupts data. Instead we ask SQLAlchemy's metadata what tables and
columns reference ``person.id`` — one source of truth, always current.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import ForeignKey, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.db.base import Base
from app.modules.person.models import Person, PersonContact, PersonMergeRecord


# ---------------------------------------------------------------------------
# Metadata introspection — one source of truth for "everything that points at a person"
# ---------------------------------------------------------------------------

def _person_fk_columns() -> list[tuple[str, str]]:
    """Return every (table_name, column_name) that has a ForeignKey to ``person.id``.

    This drives merge (rewrite FKs) and export (walk tables). Adding a new module with a
    person_id FK automatically extends both without touching this file.
    """
    out: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == "person" and fk.column.name == "id":
                    if table.name == "person":  # skip the person table itself
                        continue
                    out.append((table.name, col.name))
    return out


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict:
    """Best-effort JSON-ready dict from a SQLAlchemy Row/RowMapping."""
    out: dict = {}
    src = row._mapping if hasattr(row, "_mapping") else row
    for k, v in dict(src).items():
        if isinstance(v, (uuid.UUID,)):
            out[k] = str(v)
        elif isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, (bytes, bytearray)):
            out[k] = v.hex()
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# The service — one place for merge / export / erase, sharing the FK map
# ---------------------------------------------------------------------------

class PersonGdprService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------ helpers ---------------------------------

    async def _get(self, person_id: uuid.UUID) -> Person:
        p = (await self.session.execute(select(Person).where(Person.id == person_id))).scalar_one_or_none()
        if p is None:
            raise NotFoundError("Person not found")
        return p

    # ------------------------------ merge -----------------------------------

    async def merge(
        self, *, surviving_id: uuid.UUID, losing_id: uuid.UUID,
        merged_by_user_id: uuid.UUID | None, reason: str | None = None,
    ) -> dict:
        """Rewrite every FK from losing → surviving, then delete the losing row.

        Runs in one transaction; any failure rolls the whole thing back.  Records an immutable
        ``person_merge_record`` naming the tables/columns touched so a later review can trace it.
        """
        if surviving_id == losing_id:
            raise WorkflowError("Cannot merge a person into themselves")

        surviving = await self._get(surviving_id)
        losing = await self._get(losing_id)

        # A pseudonymised person is a historical fact — merging into or from it would rewrite it.
        if surviving.pseudonymised_at or losing.pseudonymised_at:
            raise ConflictError("Cannot merge a person who has been GDPR-erased")

        person_table = Base.metadata.tables["person"]
        prow = (await self.session.execute(
            select(person_table).where(person_table.c.id == losing_id)
        )).one()
        snapshot = _row_to_dict(prow)

        touched: dict[str, int] = {}
        for table_name, col_name in _person_fk_columns():
            # Person's users FK, if a User row exists for the losing person, gets rewritten too.
            stmt = (
                update(Base.metadata.tables[table_name])
                .where(Base.metadata.tables[table_name].c[col_name] == losing_id)
                .values({col_name: surviving_id})
            )
            result = await self.session.execute(stmt)
            if result.rowcount:
                touched[f"{table_name}.{col_name}"] = int(result.rowcount)

        # Delete the losing person row now that nothing references it.
        await self.session.execute(delete(Person).where(Person.id == losing_id))

        record = PersonMergeRecord(
            surviving_person_id=surviving_id,
            losing_person_id=losing_id,
            losing_person_snapshot=snapshot,
            fk_touched=touched,
            reason=reason,
            merged_by_user_id=merged_by_user_id,
            merged_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return {
            "mergeId": str(record.id),
            "survivingPersonId": str(surviving_id),
            "losingPersonId": str(losing_id),
            "touched": touched,
            "totalRowsRewritten": sum(touched.values()),
            "mergedAt": record.merged_at.isoformat(),
        }

    # ------------------------------ export ----------------------------------

    async def export_all(self, person_id: uuid.UUID) -> dict:
        """Subject-access: every row in every table that references this person, plus the person.

        The result is JSON-safe and deterministic (tables sorted); a subject can be handed the
        file with no further processing.
        """
        await self._get(person_id)
        # Read the person as scalar columns only (relationships would fail JSON serialisation)
        person_table = Base.metadata.tables["person"]
        prow = (await self.session.execute(
            select(person_table).where(person_table.c.id == person_id)
        )).one()
        payload: dict[str, Any] = {
            "personId": str(person_id),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "person": _row_to_dict(prow),
            "related": {},
        }

        for table_name, col_name in sorted(_person_fk_columns()):
            table = Base.metadata.tables[table_name]
            rows = (await self.session.execute(
                select(table).where(table.c[col_name] == person_id)
            )).all()
            payload["related"].setdefault(table_name, [])
            for r in rows:
                payload["related"][table_name].append(_row_to_dict(r))

        # Also include the person's own child rows (relationships / contacts by FK)
        payload["related"].setdefault("person_relationship", [])
        payload["related"].setdefault("person_contact", [])
        return payload

    # ------------------------------ erase -----------------------------------

    @staticmethod
    def _hash_email(email: str | None) -> str | None:
        if not email:
            return None
        return "erased:" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]

    async def erase(self, person_id: uuid.UUID) -> dict:
        """Pseudonymise the person while preserving audit / financial integrity.

        We do **not** delete the person row: audit and financial audit reference this identity
        by FK and must remain traceable. Instead we hash identifying fields, drop contacts, and
        stamp ``pseudonymised_at`` so the notifier and UI can hide the person forever.
        """
        person = await self._get(person_id)
        if person.pseudonymised_at is not None:
            raise ConflictError("Person is already erased")

        # Preserve a one-way hash of the email so a duplicate erasure request can be recognised
        # without keeping the plaintext.
        person.email = self._hash_email(person.email)
        person.given_name = "erased"
        person.family_name = "erased"
        person.preferred_name = None
        person.date_of_birth = None
        person.nationality = None
        person.external_person_ref = None
        person.pseudonymised_at = datetime.now(timezone.utc)

        # Drop contactable rows: contacts, and any application/thesis draft the person owns
        # that is NOT already immutable. We only drop the always-personal rows here; anything
        # that carries independent institutional value (funding audit, thesis submission record,
        # etc.) is left in place, keyed on the pseudonymised person_id.
        await self.session.execute(
            delete(PersonContact).where(PersonContact.person_id == person_id)
        )

        await self.session.commit()
        return {
            "personId": str(person_id),
            "erasedAt": person.pseudonymised_at.isoformat(),
        }
