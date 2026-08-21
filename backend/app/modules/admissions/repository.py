"""Admissions data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admissions.models import Offer


class AdmissionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_offer(self, offer_id: uuid.UUID) -> Offer | None:
        return (
            await self.session.execute(select(Offer).where(Offer.id == offer_id))
        ).scalar_one_or_none()

    async def get_offer_for_application(self, application_id: uuid.UUID) -> Offer | None:
        return (
            await self.session.execute(select(Offer).where(Offer.application_id == application_id))
        ).scalar_one_or_none()

    def add(self, offer: Offer) -> None:
        self.session.add(offer)
