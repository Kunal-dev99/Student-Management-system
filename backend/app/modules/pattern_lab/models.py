"""Pattern Lab ORM models (PL-1, plan §5 / doc §9).

Only the tables PL-1/PL-2 need: datasets and findings. Model/version/run/prediction tables
arrive with PL-3+ so nothing ships speculative and empty. The matrix is stored on the
dataset row as JSON — at institutional scale (hundreds of students × ~15 features) that is
kilobytes, and it makes a dataset version a genuinely frozen, reproducible artifact.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class MlDataset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ml_dataset"

    target_key: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(64), index=True)   # content hash — same data, same version
    status: Mapped[str] = mapped_column(String(20), default="built")  # built | insufficient
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    eligible: Mapped[int] = mapped_column(Integer, default=0)
    positives: Mapped[int] = mapped_column(Integer, default=0)
    sufficient: Mapped[bool] = mapped_column(Boolean, default=False)
    quality: Mapped[dict] = mapped_column(JSON)     # exclusions, completeness, excluded features
    matrix: Mapped[list] = mapped_column(JSON)      # [{studentId, outcome, features:{...}}]
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MlModel(UUIDMixin, TimestampMixin, Base):
    """A named predictive capability for one governed target (PL-3, doc §9 ml_models).

    A model is the stable identity ("Progression Delay Risk model"); versions carry the
    actual trained artifacts. One model per target per name.
    """
    __tablename__ = "ml_model"

    target_key: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MlTrainingRun(UUIDMixin, TimestampMixin, Base):
    """One execution of the bounded candidate search over one dataset version (doc §9)."""
    __tablename__ = "ml_training_run"

    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_model.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ml_dataset.id"), index=True)
    dataset_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed | failed
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON)      # candidates compared, baseline, verdict
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MlModelVersion(UUIDMixin, TimestampMixin, Base):
    """One trained candidate (doc §9 ml_model_versions). Lifecycle status:
    trained → candidate → review → approved → production (promotion is PL-4; training can
    only ever produce `trained`/`candidate`)."""
    __tablename__ = "ml_model_version"

    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_model.id", ondelete="CASCADE"), index=True
    )
    training_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_training_run.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    algorithm: Mapped[str] = mapped_column(String(80))
    params: Mapped[dict] = mapped_column(JSON)
    dataset_version: Mapped[str] = mapped_column(String(64))
    feature_keys: Mapped[list] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)         # CV metrics, calibration, importance
    beats_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="trained", index=True)
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # pickled pipeline
    # PL-4 — governance. Who decided what, when, and why — on the row, forever. The full
    # step-by-step trail lives in governance_log: [{action, status, byUserId, byEmail, at, rationale}].
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    governance_log: Mapped[list] = mapped_column(JSON, default=list)


class MlPrediction(UUIDMixin, TimestampMixin, Base):
    """One scored student from one batch run of one production version (PL-5, doc §9).

    Append-only: every batch keeps its rows (PL-6 monitoring needs prediction history to
    compare against actuals). Reads use the latest batch per model. Traceability is total:
    prediction → version → training run → dataset version.
    """
    __tablename__ = "ml_prediction"

    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_model.id", ondelete="CASCADE"), index=True
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_model_version.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    target_key: Mapped[str] = mapped_column(String(50))
    probability: Mapped[float] = mapped_column(Float)
    # Top contributing factors, computed per prediction:
    # [{feature, label, value, deltaPp}] — deltaPp = percentage-point change in predicted
    # probability when this feature is replaced by the population median.
    factors: Mapped[list] = mapped_column(JSON)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MlFinding(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ml_finding"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_dataset.id", ondelete="CASCADE"), index=True
    )
    feature_key: Mapped[str] = mapped_column(String(80))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    statement: Mapped[str] = mapped_column(Text)                # business-language pattern
    significant: Mapped[bool] = mapped_column(Boolean, default=False)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    effect: Mapped[float | None] = mapped_column(Float, nullable=True)   # risk ratio
    evidence: Mapped[dict] = mapped_column(JSON)                # rates, ns, split, confounders
