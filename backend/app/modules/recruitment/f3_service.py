"""F3 — services for references, interviews, and offer conditions.

These are thin CRUD services plus the gate rules that Admissions consults on issue/accept.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.recruitment.f3_models import (
    Interview, InterviewOutcome, InterviewPanellist, InterviewStatus,
    OfferCondition, OfferConditionStatus,
    ReferenceRequest, ReferenceRequestStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- references

class ReferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request(
        self, application_id: uuid.UUID, *,
        referee_name: str, referee_email: str, referee_affiliation: str | None,
    ) -> tuple[ReferenceRequest, str]:
        """Create a reference request and return (row, cleartext_token). The token is emitted
        only once, at creation — the DB stores the hash."""
        token = secrets.token_urlsafe(32)
        row = ReferenceRequest(
            application_id=application_id,
            referee_name=referee_name, referee_email=referee_email,
            referee_affiliation=referee_affiliation,
            token_hash=_hash(token), requested_at=_now(),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row, token

    async def list_for(self, application_id: uuid.UUID) -> list[ReferenceRequest]:
        return list((await self.session.execute(
            select(ReferenceRequest).where(ReferenceRequest.application_id == application_id)
            .order_by(ReferenceRequest.requested_at)
        )).scalars().all())

    async def submit(self, token: str, *, text_body: str, document_ref: str | None = None) -> ReferenceRequest:
        row = (await self.session.execute(
            select(ReferenceRequest).where(ReferenceRequest.token_hash == _hash(token))
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Reference token not recognised")
        if row.status != ReferenceRequestStatus.requested:
            raise ConflictError(f"Reference already {row.status.value}")
        row.status = ReferenceRequestStatus.received
        row.submitted_at = _now()
        row.response_text = text_body
        row.response_document_ref = document_ref
        await self.session.commit()
        await self.session.refresh(row)
        return row


# ---------------------------------------------------------------- interviews

class InterviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def schedule(
        self, application_id: uuid.UUID, *, scheduled_at: datetime,
        location: str | None = None,
    ) -> Interview:
        row = Interview(application_id=application_id, scheduled_at=scheduled_at, location=location)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_for(self, application_id: uuid.UUID) -> list[Interview]:
        return list((await self.session.execute(
            select(Interview).where(Interview.application_id == application_id)
            .order_by(Interview.scheduled_at)
        )).scalars().all())

    async def add_panellist(
        self, interview_id: uuid.UUID, *, person_id: uuid.UUID, role: str | None = None,
    ) -> InterviewPanellist:
        # Refuse duplicates cleanly (the unique index would also catch it)
        existing = (await self.session.execute(
            select(InterviewPanellist).where(
                InterviewPanellist.interview_id == interview_id,
                InterviewPanellist.person_id == person_id,
            )
        )).scalar_one_or_none()
        if existing:
            raise ConflictError("That person is already on the panel")
        row = InterviewPanellist(interview_id=interview_id, person_id=person_id, role=role)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def panellists(self, interview_id: uuid.UUID) -> list[InterviewPanellist]:
        return list((await self.session.execute(
            select(InterviewPanellist).where(InterviewPanellist.interview_id == interview_id)
        )).scalars().all())

    async def record_outcome(
        self, interview_id: uuid.UUID, *, outcome: InterviewOutcome, notes: str | None = None,
    ) -> Interview:
        row = (await self.session.execute(
            select(Interview).where(Interview.id == interview_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Interview not found")
        row.status = InterviewStatus.completed
        row.outcome = outcome
        row.notes = notes
        await self.session.commit()
        await self.session.refresh(row)
        return row


# ---------------------------------------------------------------- offer conditions

class OfferConditionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self, offer_id: uuid.UUID, *, description: str, satisfy_by: date | None,
    ) -> OfferCondition:
        row = OfferCondition(offer_id=offer_id, description=description, satisfy_by=satisfy_by)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_for(self, offer_id: uuid.UUID) -> list[OfferCondition]:
        return list((await self.session.execute(
            select(OfferCondition).where(OfferCondition.offer_id == offer_id)
            .order_by(OfferCondition.created_at)
        )).scalars().all())

    async def satisfy(
        self, condition_id: uuid.UUID, *, evidence_document_ref: str | None = None,
    ) -> OfferCondition:
        row = (await self.session.execute(
            select(OfferCondition).where(OfferCondition.id == condition_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Condition not found")
        row.status = OfferConditionStatus.satisfied
        row.satisfied_at = _now()
        if evidence_document_ref:
            row.evidence_document_ref = evidence_document_ref
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def waive(self, condition_id: uuid.UUID) -> OfferCondition:
        row = (await self.session.execute(
            select(OfferCondition).where(OfferCondition.id == condition_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Condition not found")
        row.status = OfferConditionStatus.waived
        row.satisfied_at = _now()
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def unsatisfied_past_due(self, offer_id: uuid.UUID) -> list[OfferCondition]:
        today = date.today()
        return [c for c in await self.list_for(offer_id)
                if c.status == OfferConditionStatus.pending
                and c.satisfy_by is not None and c.satisfy_by < today]

    async def any_unsatisfied(self, offer_id: uuid.UUID) -> list[OfferCondition]:
        return [c for c in await self.list_for(offer_id)
                if c.status == OfferConditionStatus.pending]
