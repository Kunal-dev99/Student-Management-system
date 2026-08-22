"""Model governance (PL-4): lifecycle, approver separation, model cards, lineage.

The lifecycle (doc §6.9):

    trained → candidate → review → approved → production
                              ↘ declined            ↘ retired

Rules that are enforced, not advised:

- **Only legal transitions run.** The map below is the whole state machine; anything else
  is a 409 naming the current status.
- **Approver separation** (the Phase 6.5 pattern): the user who *started the training run*
  cannot approve, decline or promote a version born from it. A model contested by a student
  or supervisor must be able to show that two different humans stood behind it.
- **Decisions carry rationale.** approve / decline / promote / retire all require a written
  reason; it lands on the row and in the append-only `governance_log`.
- **One production version per model.** Promotion retires the incumbent automatically, and
  says so in both versions' logs.
- **A version that failed to beat the baseline cannot even enter review.** A coin-flip with
  a version number must never acquire governance momentum.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.modules.pattern_lab.models import (
    MlDataset,
    MlModel,
    MlModelVersion,
    MlTrainingRun,
)
from app.modules.pattern_lab.targets import TARGETS

# action -> (required_from_status, to_status)
TRANSITIONS: dict[str, tuple[str, str]] = {
    "submit_review": ("candidate", "review"),
    "approve":       ("review", "approved"),
    "decline":       ("review", "declined"),
    "promote":       ("approved", "production"),
    "retire":        ("production", "retired"),
}
NEEDS_RATIONALE = {"approve", "decline", "promote", "retire"}
NEEDS_SEPARATION = {"approve", "decline", "promote"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GovernanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _version(self, version_id: uuid.UUID) -> MlModelVersion:
        v = await self.session.get(MlModelVersion, version_id)
        if v is None:
            raise NotFoundError("Model version not found")
        return v

    async def transition(self, version_id: uuid.UUID, *, action: str,
                         rationale: str | None, user_id: uuid.UUID | None,
                         user_email: str | None) -> dict:
        if action not in TRANSITIONS:
            raise ValidationAppError(
                f"Unknown action '{action}'. One of: {', '.join(sorted(TRANSITIONS))}")
        v = await self._version(version_id)
        required_from, to_status = TRANSITIONS[action]
        if v.status != required_from:
            raise ConflictError(
                f"Cannot {action.replace('_', ' ')} a version in status '{v.status}' — "
                f"it must be '{required_from}'."
            )
        if action in NEEDS_RATIONALE and not (rationale or "").strip():
            raise ValidationAppError(
                f"'{action.replace('_', ' ')}' is a recorded decision — a written rationale "
                "is required."
            )
        if action == "submit_review" and not v.beats_baseline:
            raise ConflictError(
                "This version did not beat the baseline — it cannot enter review. "
                "A model that predicts no better than the class prior must not acquire "
                "governance momentum."
            )

        if action in NEEDS_SEPARATION:
            run = await self.session.get(MlTrainingRun, v.training_run_id)
            if run is not None and run.started_by_user_id is not None \
                    and user_id is not None and run.started_by_user_id == user_id:
                raise ConflictError(
                    "Approver separation: you started the training run that produced this "
                    "version, so a different administrator must decide on it."
                )

        retired_incumbent = None
        if action == "promote":
            incumbent = (await self.session.execute(
                select(MlModelVersion).where(
                    MlModelVersion.model_id == v.model_id,
                    MlModelVersion.status == "production",
                    MlModelVersion.id != v.id,
                )
            )).scalar_one_or_none()
            if incumbent is not None:
                incumbent.status = "retired"
                incumbent.governance_log = [*(incumbent.governance_log or []), {
                    "action": "retire", "status": "retired",
                    "byUserId": str(user_id) if user_id else None, "byEmail": user_email,
                    "at": _now().isoformat(),
                    "rationale": f"Superseded by version v{v.version_no} ({v.algorithm}).",
                }]
                retired_incumbent = f"v{incumbent.version_no} ({incumbent.algorithm})"

        v.status = to_status
        entry = {
            "action": action, "status": to_status,
            "byUserId": str(user_id) if user_id else None, "byEmail": user_email,
            "at": _now().isoformat(), "rationale": (rationale or "").strip() or None,
        }
        v.governance_log = [*(v.governance_log or []), entry]
        if action in NEEDS_RATIONALE:
            v.decided_by_user_id = user_id
            v.decision_rationale = (rationale or "").strip()
            v.decided_at = _now()
        await self.session.commit()
        await self.session.refresh(v)
        return {"id": str(v.id), "status": v.status, "log": v.governance_log,
                "retiredIncumbent": retired_incumbent}

    # ------------------------------------------------------------------
    # Model card (doc §6.9) — generated from the data, never hand-written
    # ------------------------------------------------------------------

    async def model_card(self, version_id: uuid.UUID) -> dict:
        v = await self._version(version_id)
        model = await self.session.get(MlModel, v.model_id)
        run = await self.session.get(MlTrainingRun, v.training_run_id)
        ds = await self.session.get(MlDataset, run.dataset_id) if run else None
        target = TARGETS.get(model.target_key) if model else None

        metrics = v.metrics or {}
        n, pos = metrics.get("n", 0), metrics.get("positives", 0)
        auc, std = metrics.get("aucMean"), metrics.get("aucStd")

        # Limitations are computed, not curated — the card must say what a careful
        # statistician would say even when nobody wants to hear it.
        limitations = [
            "Predictions describe association, not causation; contributing factors are "
            "not levers.",
            "Trained on this institution's own history — it inherits any bias in past "
            "decisions and does not transfer to other institutions.",
        ]
        if n and n < 500:
            limitations.append(
                f"Small dataset (n={n}): estimates are volatile; expect performance to "
                "shift as cohorts grow.")
        if n and pos and pos / n < 0.2:
            limitations.append(
                f"Imbalanced outcome ({pos} of {n} positive): precision at any operating "
                "point should be checked before acting on individual predictions.")
        if auc is not None and auc < 0.7:
            limitations.append(
                f"Modest discrimination (AUC {auc:.2f}): treat as a screening aid, "
                "never as an individual judgement.")
        if std is not None and std > 0.05:
            limitations.append(
                f"Fold-to-fold variance is wide (±{std:.2f}): the headline AUC is an "
                "average, not a guarantee.")

        return {
            "versionId": str(v.id), "versionNo": v.version_no, "status": v.status,
            "model": {"id": str(model.id), "name": model.name,
                      "targetKey": model.target_key} if model else None,
            "purpose": {
                "question": target.question if target else None,
                "outcome": target.outcome_label if target else None,
                "population": target.population if target else None,
                "predictionPoint": target.prediction_point if target else None,
            },
            "data": {
                "datasetVersion": v.dataset_version,
                "builtAt": ds.created_at.isoformat() if ds and ds.created_at else None,
                "recordsFound": ds.records_found if ds else None,
                "eligible": ds.eligible if ds else None,
                "positives": ds.positives if ds else None,
                "exclusions": (ds.quality or {}).get("exclusions") if ds else None,
                "excludedFeatures": (ds.quality or {}).get("excludedFeatures") if ds else None,
            },
            "method": {
                "algorithm": v.algorithm, "params": v.params,
                "features": v.feature_keys,
                "validation": f"stratified {metrics.get('cvFolds', '?')}-fold "
                              "cross-validation, out-of-fold metrics",
            },
            "performance": {k: metrics.get(k) for k in (
                "aucMean", "aucStd", "averagePrecision", "brierScore",
                "precisionAt50", "recallAt50", "n", "positives")},
            "explainability": metrics.get("permutationImportance", []),
            "limitations": limitations,
            "governance": v.governance_log or [],
        }

    # ------------------------------------------------------------------
    # Lineage (plan success criterion 5)
    # ------------------------------------------------------------------

    async def lineage(self, version_id: uuid.UUID) -> dict:
        v = await self._version(version_id)
        model = await self.session.get(MlModel, v.model_id)
        run = await self.session.get(MlTrainingRun, v.training_run_id)
        ds = await self.session.get(MlDataset, run.dataset_id) if run else None
        return {"chain": [
            {"kind": "dataset", "id": str(ds.id) if ds else None,
             "label": ds.name if ds else "dataset",
             "sub": f"v{ds.version[:8]}… · {ds.eligible} eligible" if ds else None},
            {"kind": "features", "id": None,
             "label": f"{len(v.feature_keys or [])} features",
             "sub": "temporal-validated; exclusions on the dataset quality report"},
            {"kind": "trainingRun", "id": str(run.id) if run else None,
             "label": "candidate search",
             "sub": f"{(run.detail or {}).get('verdict')} · "
                    f"{run.duration_ms} ms" if run else None},
            {"kind": "version", "id": str(v.id),
             "label": f"v{v.version_no} {v.algorithm}", "sub": v.status},
            {"kind": "predictions", "id": None, "label": "predictions",
             "sub": "arrives with PL-5" if v.status != "production"
                    else "batch scoring arrives with PL-5"},
        ]}
