"""Research context: awards and demand (Phase 6.1 — CIO vision GAP-01).

The vision starts **before the student exists**: the institution knows it needs a researcher
because of a research award or planned activity.

    ResearchAward ──▶ ResearchDemand ──▶ ResearchOpportunity (position) ──▶ Recruitment ──▶ Student

**Scope guardrail:** `ResearchAward` is a *reference* record — award number, title, funder, dates,
headline value. Deliberately no budget lines, claims, expenditure or reporting periods: grants
management stays in the Research system, and awards normally arrive from it through the
integration hub (`source_system` set). Manual creation exists only for institutions with no
integration yet.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.research.constants import AwardStatus, DemandStatus


class ResearchAward(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_award"

    award_ref: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # funder's number
    title: Mapped[str] = mapped_column(String(400))
    funder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_source.id"), nullable=True)
    principal_investigator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("person.id"), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[AwardStatus] = mapped_column(
        Enum(AwardStatus, name="award_status"), default=AwardStatus.active
    )
    # Provenance. When source_system is set the record is mastered externally and read-only here.
    source_system: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchDemand(UUIDMixin, TimestampMixin, Base):
    """A stated need for a researcher — the object that exists before any position is advertised."""
    __tablename__ = "research_demand"

    title: Mapped[str] = mapped_column(String(300))
    # Optional: demand may be strategic (departmental growth) rather than award-driven.
    research_award_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_award.id", ondelete="SET NULL"), nullable=True, index=True
    )
    research_area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_area.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department.id"), nullable=True)
    requested_places: Mapped[int] = mapped_column(Integer, default=1)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DemandStatus] = mapped_column(
        Enum(DemandStatus, name="demand_status"), default=DemandStatus.identified, index=True
    )
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
