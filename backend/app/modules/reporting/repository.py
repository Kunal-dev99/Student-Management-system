"""Reporting read models (arch §13).

Read-only aggregations over the lifecycle tables. This is the read layer (arch §13.1) — in
production it runs against replicas + materialized views; here it computes on demand with plain
aggregations so it stays portable (SQLite/PostgreSQL). No writes.
"""
from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admissions.models import Offer
from app.modules.funding.models import FundingArrangement
from app.modules.person.models import Person
from app.modules.progression.models import Milestone
from app.modules.recruitment.models import Application, ResearchOpportunity
from app.modules.student_record.models import Student
from app.modules.thesis.models import Thesis


def _val(x) -> str:
    return x.value if hasattr(x, "value") else str(x)


class ReportingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _count(self, model) -> int:
        return int((await self.session.execute(select(func.count()).select_from(model))).scalar_one())

    async def _group(self, column) -> dict[str, int]:
        rows = (await self.session.execute(select(column, func.count()).group_by(column))).all()
        return {_val(k): int(n) for k, n in rows}

    async def totals(self) -> dict:
        return {
            "persons": await self._count(Person),
            "students": await self._count(Student),
            "applications": await self._count(Application),
            "opportunities": await self._count(ResearchOpportunity),
        }

    async def students_by_status(self) -> dict[str, int]:
        return await self._group(Student.status)

    async def applications_by_stage(self) -> dict[str, int]:
        return await self._group(Application.current_stage)

    async def offers_by_status(self) -> dict[str, int]:
        return await self._group(Offer.status)

    async def milestones_by_status(self) -> dict[str, int]:
        return await self._group(Milestone.status)

    async def theses_by_status(self) -> dict[str, int]:
        return await self._group(Thesis.status)

    async def funded_students(self) -> int:
        stmt = select(func.count(distinct(FundingArrangement.student_id))).where(
            FundingArrangement.valid_to.is_(None)
        )
        return int((await self.session.execute(stmt)).scalar_one())
