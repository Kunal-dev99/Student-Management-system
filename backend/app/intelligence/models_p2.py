"""AI-P2 — Intervention, Supervision commitment and Engagement models.

Kept in a separate module so P1 can be reasoned about (and rolled back) independently.
Every table here is derived / operational — nothing here is a source of truth. The
domain services (workflow.tasks, supervision.meetings, etc.) remain authoritative;
this layer only adds intent (plan), confirmation and observable outcomes.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


# ---- Interventions -----------------------------------------------------------

class InterventionPlan(UUIDMixin, TimestampMixin, Base):
    """A drafted or confirmed intervention over a case.

    Actions live in `intervention_action`, one row per allow-listed step. The plan
    itself carries the *intent* + rationale + reassessment cadence. Execution never
    happens on this table — the confirm endpoint dispatches through domain services
    and stores their references on the linked action rows.
    """
    __tablename__ = "intervention_plan"

    case_ref: Mapped[str] = mapped_column(String(120), index=True)
    """Free-form reference: e.g. "student:<uuid>" or "cohort:no_supervision_90d"."""

    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    """Populated when the plan is about a single student; null for cohort-scoped plans."""

    rationale: Mapped[str] = mapped_column(String(2000))
    """One-paragraph explanation the planner recorded — evidence-backed, not opinion."""

    source_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Where the plan came from: weekly_review row, manual, twin pressure point, …"""

    reassess_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    """draft | confirmed | cancelled | expired."""

    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    """case_ref + source_signal_hash — refuses duplicate draft creation."""

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InterventionAction(UUIDMixin, TimestampMixin, Base):
    """One step inside a plan — allow-listed type, target and (optional) owner."""
    __tablename__ = "intervention_action"
    __table_args__ = (
        UniqueConstraint("plan_id", "idempotency_key", name="uq_intervention_action_plan_idem"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intervention_plan.id", ondelete="CASCADE"), index=True,
    )
    action_type: Mapped[str] = mapped_column(String(60), index=True)
    """create_task | prepare_meeting_brief | request_funding_review |
       open_review_evidence_check | schedule_reassessment."""

    target_ref: Mapped[dict] = mapped_column(JSON)
    """{"kind": "...", "id": "...", "label": "..."} — what the action acts on."""

    owner_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(200))
    """Prevents duplicate execution on retries — enforced by unique constraint above."""

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    """pending | executed | failed | skipped."""

    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Domain reference the executor returned (task id, meeting id, …). Small envelope."""

    error_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class InterventionOutcome(UUIDMixin, TimestampMixin, Base):
    """Before/after snapshots recorded when a plan's reassessment fires.

    Never a causal claim — describes what changed in the observable state around the
    intervention, so the queue can label a case "HIGH → MEDIUM after actions completed".
    """
    __tablename__ = "intervention_outcome"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intervention_plan.id", ondelete="CASCADE"), index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    """Small, structured — priority score, flag counts, milestone status, funding coverage."""

    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)


# ---- Supervision commitments -------------------------------------------------

class SupervisionCommitment(UUIDMixin, TimestampMixin, Base):
    """One agreed action extracted from a supervision meeting.

    Extends the meeting record without replacing it — the meeting row remains the
    source of truth for date/format/notes. Commitments carry ownership, dependency
    and due date separately so the trajectory + intervention layers can act on them.
    """
    __tablename__ = "supervision_commitment"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("supervision_meeting.id", ondelete="CASCADE"), index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True,
    )
    text: Mapped[str] = mapped_column(String(1000))
    owner_person_or_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dependency_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """{"blocked_by": [meeting_id, …], "blocks": [meeting_id, …]} — small graph."""

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    """open | done | cancelled."""

    evidence_link: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    """manual | extractor | llm — traceability of who/what created the row."""


# ---- Engagement trajectory ---------------------------------------------------

class EngagementEvent(UUIDMixin, TimestampMixin, Base):
    """One deterministic supervision interaction fact — the trajectory's raw data.

    A time series built from these events is the "Engagement Trajectory" replacing
    the current single relationship-signal badge. LLM narration is optional on top;
    the events alone are enough to render the chart.
    """
    __tablename__ = "engagement_event"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    """meeting_logged | interval_missed | commitment_completed | context_override |
       message_exchanged | milestone_decided."""

    weight: Mapped[int] = mapped_column(Integer, default=1)
    """Contribution to trajectory score. Rules-configurable, not model-invented."""

    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EngagementSnapshot(UUIDMixin, TimestampMixin, Base):
    """One computed trajectory point — persists what the badge said + why it moved."""
    __tablename__ = "engagement_snapshot"
    __table_args__ = (
        UniqueConstraint("student_id", "computed_at",
                          name="uq_engagement_snapshot_student_computed"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    label: Mapped[str] = mapped_column(String(30))
    """thriving | steady | drifting | strained — same vocab as the current badge."""

    score: Mapped[int] = mapped_column(Integer)
    """Bounded integer, e.g. -100..100. The chart plots this."""

    drivers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Recent events summarised: {"missed_interval": 2, "meeting_logged": 3, …}."""

    engine: Mapped[str] = mapped_column(String(20), default="rules")
    """rules | llm — which produced the label (never both, no averaging)."""
