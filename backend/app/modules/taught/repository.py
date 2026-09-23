"""Taught-lifecycle data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.taught.models import (
    AssessmentResult,
    Dissertation,
    ModuleAssessment,
    ModuleEnrolment,
    ModuleOffering,
    TaughtAward,
    TaughtModule,
)


class TaughtRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- modules / assessments ---
    async def modules_for_programme(self, programme_id: uuid.UUID) -> list[TaughtModule]:
        res = await self.session.execute(
            select(TaughtModule)
            .where(TaughtModule.programme_id == programme_id)
            .order_by(TaughtModule.code)
        )
        return list(res.scalars().unique().all())

    async def elective_modules_for_programme(self, programme_id: uuid.UUID) -> list[TaughtModule]:
        """Modules OFFERED on this programme as electives (home programme is a different one)."""
        res = await self.session.execute(
            select(TaughtModule)
            .join(ModuleOffering, ModuleOffering.module_id == TaughtModule.id)
            .where(ModuleOffering.programme_id == programme_id)
            .order_by(TaughtModule.code)
        )
        return list(res.scalars().unique().all())

    async def all_modules(self) -> list[TaughtModule]:
        res = await self.session.execute(select(TaughtModule).order_by(TaughtModule.code))
        return list(res.scalars().unique().all())

    async def get_offering(self, programme_id: uuid.UUID, module_id: uuid.UUID) -> ModuleOffering | None:
        return (await self.session.execute(
            select(ModuleOffering).where(
                ModuleOffering.programme_id == programme_id,
                ModuleOffering.module_id == module_id,
            )
        )).scalar_one_or_none()

    async def get_module(self, module_id: uuid.UUID) -> TaughtModule | None:
        return (await self.session.execute(
            select(TaughtModule).where(TaughtModule.id == module_id)
        )).scalar_one_or_none()

    async def get_assessment(self, assessment_id: uuid.UUID) -> ModuleAssessment | None:
        return (await self.session.execute(
            select(ModuleAssessment).where(ModuleAssessment.id == assessment_id)
        )).scalar_one_or_none()

    # --- enrolments / results ---
    async def enrolments_for_student(self, student_id: uuid.UUID) -> list[ModuleEnrolment]:
        res = await self.session.execute(
            select(ModuleEnrolment)
            .where(ModuleEnrolment.student_id == student_id)
            .options(selectinload(ModuleEnrolment.results))
            .order_by(ModuleEnrolment.academic_year, ModuleEnrolment.created_at)
        )
        return list(res.scalars().unique().all())

    async def get_enrolment(self, enrolment_id: uuid.UUID) -> ModuleEnrolment | None:
        return (await self.session.execute(
            select(ModuleEnrolment)
            .where(ModuleEnrolment.id == enrolment_id)
            .options(selectinload(ModuleEnrolment.results))
        )).scalar_one_or_none()

    async def existing_enrolment(
        self, student_id: uuid.UUID, module_id: uuid.UUID, academic_year: str
    ) -> ModuleEnrolment | None:
        return (await self.session.execute(
            select(ModuleEnrolment).where(
                ModuleEnrolment.student_id == student_id,
                ModuleEnrolment.module_id == module_id,
                ModuleEnrolment.academic_year == academic_year,
            )
        )).scalar_one_or_none()

    # --- dissertation / award ---
    async def get_dissertation(self, student_id: uuid.UUID) -> Dissertation | None:
        return (await self.session.execute(
            select(Dissertation).where(Dissertation.student_id == student_id)
        )).scalar_one_or_none()

    async def get_award(self, student_id: uuid.UUID) -> TaughtAward | None:
        return (await self.session.execute(
            select(TaughtAward).where(TaughtAward.student_id == student_id)
        )).scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)
