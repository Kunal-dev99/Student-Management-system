"""Evidence writes + freshness reads.

Every producer that emits an AI answer should also emit its supporting `EvidenceClaim`
rows in the SAME request — batched via `record_many`. Later, when a user opens the
answer, `for_artefact` returns the claims with an `is_stale` flag computed by
re-hashing the current source value against the recorded `value_hash`.

Stale-ness detection is intentionally simple in Phase 1 — Phase 3+ can add per-source
resolvers that reach into domain services to compute the current hash without a full
row read. Today the frontend interprets `is_stale=None` as "not checked".
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import EvidenceClaim
from app.intelligence.schemas import EvidenceClaimCreate


def evidence_hash(value: object) -> str:
    """Deterministic SHA-256 over a JSON-serialisable value.

    Booleans, ints, floats, strings, dates/datetimes-as-string, and dict/list of the
    above are stable across processes because `sort_keys=True` fixes dict order and
    `default=str` handles UUIDs / datetimes without exploding.
    """
    encoded = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class EvidenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_many(self, claims: Iterable[EvidenceClaimCreate]) -> list[uuid.UUID]:
        """Persist a batch of claims for one artefact. Returns their new ids."""
        rows: list[EvidenceClaim] = []
        for c in claims:
            row = EvidenceClaim(
                artefact_id=c.artefact_id,
                claim_type=c.claim_type,
                source_type=c.source_type,
                source_id=c.source_id,
                locator=c.locator,
                value_hash=c.value_hash,
                as_of=c.as_of,
                status=c.status,
                # `permission_scope` and `detail` are JSON, and Pydantic hands us Python dicts.
                # We store as-is (Postgres JSON column round-trips them).
                detail=c.detail,
            )
            # Store permission_scope inside detail to keep the schema simple in P1 —
            # a future migration can promote it to its own column when queries need it.
            if c.permission_scope is not None:
                row.detail = {"__permission_scope": c.permission_scope, **(c.detail or {})}
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return [r.id for r in rows]

    async def for_artefact(self, artefact_id: uuid.UUID) -> list[EvidenceClaim]:
        """Every claim recorded against one artefact, oldest first (audit order)."""
        stmt = (
            select(EvidenceClaim)
            .where(EvidenceClaim.artefact_id == artefact_id)
            .order_by(EvidenceClaim.created_at.asc())
        )
        return (await self.session.execute(stmt)).scalars().all()
