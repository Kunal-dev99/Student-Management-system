"""Model monitoring (PL-6): performance vs actuals, drift, and the retrain loop.

Three questions, answered from data the platform already keeps:

1. **Is it still right?** Predictions are append-only, and outcomes mature: a student who
   was scored months ago may now have a knowable outcome. Matured predictions are compared
   against what actually happened — realised outcome rate per predicted-probability band
   (calibration in the wild) and AUC on the matured subset, computed with a rank statistic
   (Mann–Whitney), so monitoring needs no ML dependency at all.

2. **Is the world still the one it learned?** Population drift per feature via PSI between
   the training dataset's stored matrix (the frozen artifact pays off here) and the current
   cohort. Standard bands: <0.1 stable, 0.1–0.25 moderate, ≥0.25 major.

3. **When should a human look?** A recommended review date (`pattern_lab.review_interval_days`,
   a Phase 8 setting) pulled earlier by named signals: major drift, or matured AUC falling
   well below the training estimate. The output is a date and reasons — never an automatic
   action.

**Retraining is manual-first** (plan §6): `retrain()` builds a fresh dataset and re-runs the
candidate search under the same model name. The new version enters at CANDIDATE and walks
the same governance as any other — nothing auto-promotes, and scheduled/triggered retraining
is deliberately deferred until at least one manual cycle has been observed end-to-end.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.pattern_lab.dataset import DatasetBuilder
from app.modules.pattern_lab.features import FEATURES
from app.modules.pattern_lab.models import (
    MlDataset,
    MlModel,
    MlModelVersion,
    MlPrediction,
)

PSI_MODERATE = 0.1
PSI_MAJOR = 0.25
AUC_DROP_TOLERANCE = 0.10
MIN_MATURED = 20            # below this, actuals are reported but not judged


def _auc(pairs: list[tuple[float, int]]) -> float | None:
    """AUC via the rank statistic — no sklearn needed for monitoring."""
    pos = [p for p, y in pairs if y == 1]
    neg = [p for p, y in pairs if y == 0]
    if not pos or not neg:
        return None
    ranked = sorted(pairs, key=lambda t: t[0])
    # average ranks with tie handling
    ranks: dict[int, float] = {}
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    rank_sum_pos = sum(r for k, r in ranks.items() if ranked[k][1] == 1)
    u = rank_sum_pos - len(pos) * (len(pos) + 1) / 2
    return round(u / (len(pos) * len(neg)), 4)


def _psi(train: list[float], current: list[float]) -> float | None:
    """Population stability index between two samples of one feature."""
    train = [v for v in train if v is not None]
    current = [v for v in current if v is not None]
    if len(train) < 10 or len(current) < 10:
        return None
    lo = sorted(train)
    if lo[0] == lo[-1]:
        return 0.0 if all(v == lo[0] for v in current) else 1.0
    # quintile edges from the TRAINING distribution
    edges = [lo[min(len(lo) - 1, int(len(lo) * q / 5))] for q in range(1, 5)]
    def bin_of(v: float) -> int:
        for i, e in enumerate(edges):
            if v <= e:
                return i
        return 4
    eps = 1e-4
    psi = 0.0
    for b in range(5):
        p = max(sum(1 for v in train if bin_of(v) == b) / len(train), eps)
        q = max(sum(1 for v in current if bin_of(v) == b) / len(current), eps)
        psi += (q - p) * math.log(q / p)
    return round(psi, 4)


class MonitoringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def overview(self) -> list[dict]:
        from app.modules.settings.service import setting_value

        review_days = await setting_value(self.session, "pattern_lab.review_interval_days")
        models = (await self.session.execute(
            select(MlModel).order_by(MlModel.created_at.desc())
        )).scalars().all()
        out = []
        for m in models:
            version = (await self.session.execute(
                select(MlModelVersion).where(
                    MlModelVersion.model_id == m.id,
                    MlModelVersion.status == "production",
                )
            )).scalar_one_or_none()
            if version is None:
                continue
            out.append(await self._monitor_one(m, version, review_days))
        return out

    async def _monitor_one(self, m: MlModel, version: MlModelVersion,
                           review_days: int) -> dict:
        builder = DatasetBuilder(self.session)
        feature_defs = {f.key: f for f in FEATURES}
        keys = version.feature_keys or []

        # ---- prediction trend: every batch, oldest first ----
        preds = (await self.session.execute(
            select(MlPrediction).where(MlPrediction.model_id == m.id)
            .order_by(MlPrediction.scored_at)
        )).scalars().all()
        batches: dict[uuid.UUID, list[MlPrediction]] = {}
        for p in preds:
            batches.setdefault(p.batch_id, []).append(p)
        trend = []
        for batch_id, rows in batches.items():
            probs = [r.probability for r in rows]
            bins = [0] * 5
            for p in probs:
                bins[min(4, int(p * 5))] += 1
            trend.append({
                "batchId": str(batch_id),
                "scoredAt": rows[0].scored_at.isoformat() if rows[0].scored_at else None,
                "scored": len(rows),
                "meanProbability": round(sum(probs) / len(probs), 4),
                "bands": bins,
            })
        trend.sort(key=lambda t: t["scoredAt"] or "")

        # ---- performance vs actuals on the OLDEST batch (most matured) ----
        actuals = None
        if batches:
            oldest = min(batches.values(),
                         key=lambda rows: rows[0].scored_at or rows[0].created_at)
            from app.modules.settings.service import setting_value
            min_gap = await setting_value(self.session, "funding.min_gap_days")
            contexts = {c.student.id: c for c in await builder._contexts()}
            matured_pairs, band_stats = [], [
                {"band": f"{i*20}–{i*20+20}%", "n": 0, "positives": 0} for i in range(5)]
            for p in oldest:
                ctx = contexts.get(p.student_id)
                if ctx is None:
                    continue
                outcome, _, excl = builder._label(m.target_key, ctx, min_gap)
                if excl is not None:
                    continue            # outcome still not knowable — not matured
                matured_pairs.append((p.probability, int(bool(outcome))))
                b = band_stats[min(4, int(p.probability * 5))]
                b["n"] += 1
                b["positives"] += int(bool(outcome))
            for b in band_stats:
                b["realizedRate"] = round(b["positives"] / b["n"], 3) if b["n"] else None
            actuals = {
                "batchScoredAt": oldest[0].scored_at.isoformat() if oldest[0].scored_at else None,
                "matured": len(matured_pairs),
                "aucOnMatured": _auc(matured_pairs),
                "realizedByBand": band_stats,
                "judged": len(matured_pairs) >= MIN_MATURED,
                "note": None if len(matured_pairs) >= MIN_MATURED else
                        f"Only {len(matured_pairs)} predictions have matured — reported, "
                        f"not judged (needs ≥{MIN_MATURED}).",
            }

        # ---- drift: training matrix vs the current cohort ----
        train_ds = (await self.session.execute(
            select(MlDataset).where(MlDataset.version == version.dataset_version)
            .order_by(MlDataset.created_at.desc()).limit(1)
        )).scalars().first()
        drift = []
        if train_ds is not None:
            contexts = await builder._contexts()
            today = date.today()
            current_rows = []
            for ctx in contexts:
                status = getattr(ctx.student, "status", None)
                status = status.value if hasattr(status, "value") else str(status)
                if status in ("active", "registered"):
                    current_rows.append({
                        k: (lambda v: 1.0 if v is True else 0.0 if v is False
                            else float(v) if v is not None else None)(
                            feature_defs[k].compute(ctx, today))
                        for k in keys})
            for k in keys:
                train_vals = [r["features"].get(k) for r in train_ds.matrix]
                cur_vals = [r.get(k) for r in current_rows]
                psi = _psi(train_vals, cur_vals)
                drift.append({
                    "feature": k, "label": feature_defs[k].label,
                    "psi": psi,
                    "band": None if psi is None else
                            ("major" if psi >= PSI_MAJOR else
                             "moderate" if psi >= PSI_MODERATE else "stable"),
                })
            drift.sort(key=lambda d: -(d["psi"] or -1))

        # ---- health verdict + review date, with reasons a human can check ----
        reasons = []
        trained_auc = (version.metrics or {}).get("aucMean")
        if actuals and actuals["judged"] and actuals["aucOnMatured"] is not None \
                and trained_auc is not None \
                and actuals["aucOnMatured"] < trained_auc - AUC_DROP_TOLERANCE:
            reasons.append(
                f"Matured AUC {actuals['aucOnMatured']:.2f} is well below the training "
                f"estimate {trained_auc:.2f}.")
        major = [d for d in drift if d["band"] == "major"]
        if major:
            reasons.append("Major population drift in: "
                           + ", ".join(d["label"] for d in major[:4]) + ".")
        health = "review" if reasons else (
            "watch" if any(d["band"] == "moderate" for d in drift) else "ok")
        last_scored = trend[-1]["scoredAt"] if trend else None
        base = date.fromisoformat(last_scored[:10]) if last_scored else date.today()
        review_at = date.today() if reasons else base + timedelta(days=review_days)

        return {
            "modelId": str(m.id), "modelName": m.name, "targetKey": m.target_key,
            "versionNo": version.version_no, "versionId": str(version.id),
            "trainedAuc": trained_auc,
            "health": health, "reasons": reasons,
            "recommendedReviewAt": review_at.isoformat(),
            "trend": trend, "actuals": actuals, "drift": drift,
            "note": "Monitoring recommends; it never acts. Retraining produces a new "
                    "CANDIDATE that walks the same governance as any other version.",
        }

    # ------------------------------------------------------------------
    # Manual-first retraining
    # ------------------------------------------------------------------

    async def retrain(self, model_id: uuid.UUID, user_id: uuid.UUID | None) -> dict:
        """Fresh dataset → same candidate search → new versions at TRAINED/CANDIDATE.

        Deliberately just composition: the dataset builder and training service already
        enforce sufficiency and honesty, and governance still stands between the new
        candidate and production. Scheduled/triggered retraining stays out until a manual
        cycle has been observed end-to-end (plan §6).
        """
        from app.modules.pattern_lab.training import TrainingService

        model = await self.session.get(MlModel, model_id)
        if model is None:
            raise NotFoundError("Model not found")
        if model.target_key not in ("progression_delay", "funding_continuity"):
            raise ConflictError("This model's target cannot be rebuilt yet.")
        ds = await DatasetBuilder(self.session).build(model.target_key, user_id)
        result = await TrainingService(self.session).train(
            ds.id, name=model.name, user_id=user_id)
        return {**result, "datasetVersion": ds.version,
                "note": "Retrained on a fresh dataset. The recommended version is a "
                        "CANDIDATE — it must pass review and approval before it can "
                        "replace the production version."}
