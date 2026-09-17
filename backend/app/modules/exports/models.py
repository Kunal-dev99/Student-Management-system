"""Export job model (arch §13.4).

An export runs as an async job on the worker tier writing to the object store. Here there is no
worker/object-store, so the job runs on request and the CSV is stored on the row; the client
polls the job then downloads. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.exports.constants import AdvisoryStatus, ExportStatus, SpecVersionStatus


class ExportJob(UUIDMixin, Base):
    __tablename__ = "export_job"

    kind: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[ExportStatus] = mapped_column(Enum(ExportStatus, name="export_status"), default=ExportStatus.queued)
    filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)   # CSV (stand-in for object store)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Phase 6.6 — statutory reporting as configuration (CIO vision GAP-05) ---

class ReportProfile(UUIDMixin, TimestampMixin, Base):
    """A statutory return, versioned by academic year (e.g. HESA Student 2026/27).

    Treating the return as configuration means a statutory change is a data edit, not a code
    change — and a prior year can be regenerated from the mapping that was in force then.
    """
    __tablename__ = "report_profile"

    code: Mapped[str] = mapped_column(String(40), index=True)          # e.g. HESA_STUDENT
    name: Mapped[str] = mapped_column(String(200))
    academic_year: Mapped[str] = mapped_column(String(9), index=True)  # e.g. 2026/27
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # F1 — sign-off. A profile becomes read-only once the responsible owner (Registry / HESA SME)
    # has attested that the mappings are complete for the return. Unsigning is a deliberate,
    # audited action; you cannot edit a signed-off profile until it is unsigned.
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_off_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cross-field / format rules the admin has SUPPRESSED for THIS profile only. Each entry is a
    # dict {ruleKey, reason, at, byUserId, byUserName} — a full audit record so sign-off can
    # attest to what was inhibited and why. Column name kept as `muted_rule_keys` for backward
    # compatibility of the migration lineage; the API surface talks about "suppressions".
    muted_rule_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (Index("uq_report_profile_version", "code", "academic_year", "version", unique=True),)


class ReportFieldMapping(UUIDMixin, TimestampMixin, Base):
    """One target field of a statutory return, and where its value comes from."""
    __tablename__ = "report_field_mapping"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_profile.id", ondelete="CASCADE"), index=True
    )
    target_field: Mapped[str] = mapped_column(String(80))       # the column the return expects
    position: Mapped[int] = mapped_column(Integer, default=0)   # column order in the file
    source_expression: Mapped[str] = mapped_column(String(200))  # dotted path, e.g. person.nationality
    transform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_values: Mapped[list | None] = mapped_column(JSON, nullable=True)


# --- ICR G5 — statutory advisory ingestion ---------------------------------

class StatutoryAdvisory(UUIDMixin, TimestampMixin, Base):
    """A published statutory advisory the Registry has ingested for review.

    The advisory's raw text is parsed into a deterministic set of proposed ``changes`` diffed
    against the current spec pack, together with the full ``proposed_fields``/``proposed_rules``
    that would result. Nothing takes effect until a Registry owner *accepts* it — acceptance
    materialises a new active ``StatutorySpecVersion``. This is deliberately a human-gated
    ingest→recommend→accept flow, never a live scraper.
    """
    __tablename__ = "statutory_advisory"

    pack_code: Mapped[str] = mapped_column(String(40), index=True)     # e.g. HESA_STUDENT
    academic_year: Mapped[str] = mapped_column(String(9), index=True)  # e.g. 2027/28
    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)                        # the advisory as pasted/uploaded
    source: Mapped[str] = mapped_column(String(20), default="paste")   # paste | upload
    status: Mapped[AdvisoryStatus] = mapped_column(
        Enum(AdvisoryStatus, name="advisory_status"), default=AdvisoryStatus.ingested, index=True
    )
    base_version: Mapped[int] = mapped_column(Integer, default=1)      # pack version diffed against
    parse_source: Mapped[str] = mapped_column(String(20), default="directive")  # directive | model
    # The deterministic diff and the resulting pack, stored as JSON so the review UI and the
    # accept step read exactly what was proposed at ingest time.
    changes: Mapped[list] = mapped_column(JSON, default=list)
    proposed_fields: Mapped[list] = mapped_column(JSON, default=list)
    proposed_rules: Mapped[list] = mapped_column(JSON, default=list)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class StatutorySpecVersion(UUIDMixin, TimestampMixin, Base):
    """A DB-backed spec-pack version — the result of accepting an advisory.

    The code catalogue (``specs.SPEC_PACKS``) is the baseline (version 1). Each accepted advisory
    writes a new version here; the resolver overlays the latest ``active`` version on the baseline,
    so ``from_spec``, validation and the sign-off gate all pick it up without a code change.
    """
    __tablename__ = "statutory_spec_version"

    pack_code: Mapped[str] = mapped_column(String(40), index=True)
    academic_year: Mapped[str] = mapped_column(String(9), index=True)
    version: Mapped[int] = mapped_column(Integer, default=2)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[SpecVersionStatus] = mapped_column(
        Enum(SpecVersionStatus, name="spec_version_status"), default=SpecVersionStatus.active, index=True
    )
    fields: Mapped[list] = mapped_column(JSON, default=list)
    rules: Mapped[list] = mapped_column(JSON, default=list)
    # Rule keys inhibited at the PACK level — fixes every profile using this pack version. Used
    # when an accepted advisory shipped a bad rule and per-profile suppression would be repetitive.
    disabled_rule_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_advisory_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("statutory_advisory.id", ondelete="SET NULL"), nullable=True
    )
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("uq_spec_version", "pack_code", "academic_year", "version", unique=True),
    )
