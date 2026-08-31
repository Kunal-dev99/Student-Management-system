"""ICR module-owned ORM models.

Everything in this file is ICR-specific and orthogonal to the core lifecycle:
- ClinicalPlacement (gap 2): a Specialist Registrar rotation post held alongside the studentship.
- IndependentTutor (gap 3): the outside-the-lab tutor relationship + private tutor notes.
- BenchFeeAllocation + BenchFeeDrawdown (gap 4): per-student experimental budget.
- PartnerAffiliation (gap 5): Royal Marsden / Imperial etc. with dates + compliance flags.

Every table hangs off ``student.id`` with ``ON DELETE CASCADE`` so an erased or merged student
does not orphan ICR data.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


# --- Gap 2 -----------------------------------------------------------------

class ClinicalPlacement(UUIDMixin, TimestampMixin, Base):
    """A Specialist Registrar rotation post held alongside an ICR MD(Res) studentship.

    Recorded here (not in supervision or student_record) because it is a clinical-training fact
    about the person, not a change to their student record. Overlap with the studentship is fine:
    the whole point of the clinical MD(Res) model is that both run in parallel.
    """
    __tablename__ = "icr_clinical_placement"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    trust_name: Mapped[str] = mapped_column(String(200))          # e.g. "Royal Marsden NHS Foundation Trust"
    specialty: Mapped[str] = mapped_column(String(120))           # e.g. "Medical Oncology"
    grade: Mapped[str] = mapped_column(String(60))                # e.g. "ST5", "Clinical Fellow"
    supervisor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # NHS-side clinical supervisor
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # NULL = current
    sessions_per_week: Mapped[int | None] = mapped_column(nullable=True)  # e.g. 4 clinical / 6 research
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# --- Gap 3 -----------------------------------------------------------------

class IndependentTutor(UUIDMixin, TimestampMixin, Base):
    """Outside-the-lab tutor for an ICR student.

    The invariant enforced by the service: ``tutor_person`` must not share the student's
    department. This is checked at assignment time in ``IndependentTutorService.assign()``.
    """
    __tablename__ = "icr_independent_tutor"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    tutor_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), index=True
    )
    tutor_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_icr_independent_tutor_current", "student_id", "tutor_person_id", "ended_at"),
    )


class IndependentTutorNote(UUIDMixin, TimestampMixin, Base):
    """A private tutor-notes channel — visible only to the tutor and admins, not the supervisor.

    The service enforces read access; storage is plain, but the API guards on identity.
    """
    __tablename__ = "icr_independent_tutor_note"

    tutor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("icr_independent_tutor.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    authored_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# --- Gap 4 -----------------------------------------------------------------

class BenchFeeAllocation(UUIDMixin, TimestampMixin, Base):
    """A per-student experimental budget separate from the stipend.

    Draw-downs (sequencing runs, mass-spec time) are recorded against the allocation.
    """
    __tablename__ = "icr_bench_fee_allocation"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    funding_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("funding_source.id", ondelete="SET NULL"), nullable=True
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    cost_centre: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BenchFeeDrawdown(UUIDMixin, TimestampMixin, Base):
    """One draw-down against a bench-fee allocation."""
    __tablename__ = "icr_bench_fee_drawdown"

    allocation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("icr_bench_fee_allocation.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str] = mapped_column(String(60))       # e.g. "sequencing", "mass_spec", "reagents"
    description: Mapped[str] = mapped_column(String(300))
    drawn_at: Mapped[date] = mapped_column(Date)
    invoice_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)


# --- Gap 5 -----------------------------------------------------------------

class PartnerAffiliation(UUIDMixin, TimestampMixin, Base):
    """A student's affiliation with a partner institution (Royal Marsden honorary contract,
    Imperial co-registration, etc.) — dates + compliance flags.

    Compliance is stored as JSON so each affiliation kind can carry its own set: e.g. NHS
    research passport with expiry date, DBS renewal date, GMC number, honorary contract number.
    """
    __tablename__ = "icr_partner_affiliation"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    partner_name: Mapped[str] = mapped_column(String(200))    # e.g. "Royal Marsden NHS Foundation Trust"
    affiliation_kind: Mapped[str] = mapped_column(String(60)) # "honorary_contract" | "co_registration" | "clinical_placement"
    partner_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)  # partner-side id, e.g. contract number
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    compliance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ``compliance`` example:
    # {"nhsResearchPassportExpiresOn": "2026-08-31", "dbsRenewalOn": "2027-01-15",
    #  "gmcNumber": "1234567", "occupationalHealthClearedOn": "2025-09-01"}
    active: Mapped[bool] = mapped_column(Boolean, default=True)
