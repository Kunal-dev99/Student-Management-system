"""Recruitment ORM models (arch §8.4). Portable types only (D-04)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.recruitment.constants import (
    ApplicationRoute,
    CandidateStage,
    OpportunityStatus,
)


class ResearchOpportunity(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_opportunity"

    title: Mapped[str] = mapped_column(String(300))
    research_area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_area.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department.id"), nullable=True)
    principal_supervisor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("person.id"), nullable=True)
    stipend_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    eligibility: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    positions_available: Mapped[int] = mapped_column(Integer, default=1)
    # Phase 6.1 — provenance: the demand this position answers, and the award funding it.
    # Both optional: a position may be raised directly, and demand may be strategic (no award).
    research_demand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_demand.id", ondelete="SET NULL"), nullable=True, index=True
    )
    research_award_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_award.id", ondelete="SET NULL"), nullable=True, index=True
    )
    positions_filled: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, name="opportunity_status"), default=OpportunityStatus.draft
    )


class Application(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "application"

    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    route: Mapped[ApplicationRoute] = mapped_column(Enum(ApplicationRoute, name="application_route"))
    research_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_opportunity.id"), nullable=True
    )
    research_area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_area.id"), nullable=True)
    proposal_document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    current_stage: Mapped[CandidateStage] = mapped_column(
        Enum(CandidateStage, name="candidate_stage"), default=CandidateStage.applicant
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    history: Mapped[list["CandidateStageHistory"]] = relationship(
        back_populates="application", lazy="selectin", cascade="all, delete-orphan"
    )
    assessments: Mapped[list["ApplicationAssessment"]] = relationship(
        back_populates="application", lazy="selectin", cascade="all, delete-orphan"
    )


class CandidateStageHistory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "candidate_stage_history"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    from_stage: Mapped[CandidateStage | None] = mapped_column(
        Enum(CandidateStage, name="candidate_stage"), nullable=True
    )
    to_stage: Mapped[CandidateStage] = mapped_column(Enum(CandidateStage, name="candidate_stage"))
    moved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="history")


class ApplicationAssessment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "application_assessment"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    assessor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="assessments")
