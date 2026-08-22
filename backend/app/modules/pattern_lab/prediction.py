"""Batch prediction (PL-5): score the current cohort with a PRODUCTION version.

Rules that hold:

- **Only a production version scores.** Governance is the gate to influence — a candidate,
  however good its AUC, produces nothing a user can see.
- **Predictions are advisory rows.** A batch writes `ml_prediction` and (optionally) raises
  review *tasks*; it never touches a student record. Rules and humans stay the decision
  layer (doc §10/§13).
- **Every prediction explains itself.** Per-student contributing factors are computed by
  perturbation: replace one feature with the population median and measure how the
  predicted probability moves. "Funding active: −12 pp" is model-agnostic, exact for this
  student, and needs no extra dependency.
- **Task raising is off by default** and controlled by two Phase 8 institution settings
  (`pattern_lab.raise_tasks`, `pattern_lab.task_threshold`). When on, one open task per
  (student, model) — a rescore never duplicates an unactioned task.

Batches run in-request (seconds at institutional scale), following the platform's
endpoint-triggered stand-in pattern for worker jobs; the rows are append-only so PL-6 can
compare batches against actual outcomes later.
"""
from __future__ import annotations

import pickle
import time
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.modules.pattern_lab.dataset import DatasetBuilder
from app.modules.pattern_lab.features import FEATURES
from app.modules.pattern_lab.models import MlModel, MlModelVersion, MlPrediction
from app.modules.pattern_lab.targets import TARGETS

TOP_FACTORS = 4


class PredictionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _production_version(self, model_id: uuid.UUID) -> tuple[MlModel, MlModelVersion]:
        model = await self.session.get(MlModel, model_id)
        if model is None:
            raise NotFoundError("Model not found")
        version = (await self.session.execute(
            select(MlModelVersion).where(
                MlModelVersion.model_id == model_id,
                MlModelVersion.status == "production",
            )
        )).scalar_one_or_none()
        if version is None:
            raise ConflictError(
                f"'{model.name}' has no production version. Only a version that has been "
                "approved and promoted through governance can score students."
            )
        return model, version

    async def score(self, model_id: uuid.UUID) -> dict:
        from app.modules.pattern_lab.training import sklearn_available

        if not sklearn_available():
            raise ValidationAppError(
                "Batch scoring needs the optional ML extra (pip install scikit-learn)."
            )
        import numpy as np

        t0 = time.perf_counter()
        model, version = await self._production_version(model_id)
        if version.artifact is None:
            raise ValidationAppError("This version has no stored artifact.")
        pipeline = pickle.loads(version.artifact)

        # Current-cohort features, as of today. No outcome labelling — that is the point:
        # we are predicting precisely the students whose outcome is not yet knowable.
        keys = version.feature_keys or []
        feature_defs = {f.key: f for f in FEATURES}
        cutoff = date.today()
        contexts = await DatasetBuilder(self.session)._contexts()

        students, rows = [], []
        for ctx in contexts:
            status = getattr(ctx.student, "status", None)
            status = status.value if hasattr(status, "value") else str(status)
            if status not in ("active", "registered"):
                continue        # predict for the live cohort only
            feats = {}
            for k in keys:
                v = feature_defs[k].compute(ctx, cutoff)
                feats[k] = (1.0 if v is True else 0.0 if v is False
                            else float(v) if v is not None else np.nan)
            students.append(ctx)
            rows.append([feats[k] for k in keys])

        if not rows:
            raise ValidationAppError("No active students to score.")
        X = np.array(rows, dtype=float)
        proba = pipeline.predict_proba(X)[:, 1]

        # Perturbation contributions: one predict per feature, vectorised over students.
        medians = np.nanmedian(X, axis=0)
        deltas = np.zeros_like(X)
        for j in range(len(keys)):
            Xj = X.copy()
            Xj[:, j] = medians[j]
            deltas[:, j] = proba - pipeline.predict_proba(Xj)[:, 1]

        batch_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        for i, ctx in enumerate(students):
            order = np.argsort(-np.abs(deltas[i]))[:TOP_FACTORS]
            factors = [{
                "feature": keys[j],
                "label": feature_defs[keys[j]].label,
                "value": None if np.isnan(X[i, j]) else round(float(X[i, j]), 2),
                "deltaPp": round(float(deltas[i, j]) * 100, 1),
            } for j in order if abs(deltas[i][j]) >= 0.001]
            self.session.add(MlPrediction(
                model_id=model.id, model_version_id=version.id, batch_id=batch_id,
                student_id=ctx.student.id, target_key=model.target_key,
                probability=round(float(proba[i]), 4), factors=factors, scored_at=now,
            ))

        tasks_raised = await self._maybe_raise_tasks(model, students, proba)
        await self.session.commit()
        return {
            "batchId": str(batch_id), "modelId": str(model.id),
            "versionNo": version.version_no, "scored": len(students),
            "meanProbability": round(float(np.mean(proba)), 4),
            "highRisk": int((proba >= 0.7).sum()),
            "tasksRaised": tasks_raised,
            "durationMs": int((time.perf_counter() - t0) * 1000),
        }

    async def _maybe_raise_tasks(self, model: MlModel, students, proba) -> int:
        from app.modules.settings.service import setting_value
        from app.modules.workflow.constants import OPEN_TASK_STATES
        from app.modules.workflow.engine import WorkflowEngine
        from app.modules.workflow.models import Task

        if not await setting_value(self.session, "pattern_lab.raise_tasks"):
            return 0
        threshold = await setting_value(self.session, "pattern_lab.task_threshold")
        target = TARGETS[model.target_key]
        engine = WorkflowEngine(self.session)
        raised = 0
        for ctx, p in zip(students, proba):
            if p < threshold:
                continue
            open_task = (await self.session.execute(
                select(Task).where(
                    Task.aggregate_type == "ml_prediction",
                    Task.aggregate_id == ctx.student.id,
                    Task.status.in_(OPEN_TASK_STATES),
                    Task.title.like(f"%{model.name}%"),
                )
            )).scalars().first()
            if open_task is not None:
                continue        # an unactioned task already asks for this look
            name = f"{ctx.person.given_name} {ctx.person.family_name}"
            engine.create_task(
                title=f"Review predicted risk ({model.name}): {name}",
                assignee_role="PGR Administrator",
                aggregate_type="ml_prediction", aggregate_id=ctx.student.id,
                payload={
                    "studentId": str(ctx.student.id), "studentName": name,
                    "probability": round(float(p), 3), "modelName": model.name,
                    "outcome": target.outcome_label,
                    "note": "Advisory prediction — a human decides what, if anything, "
                            "happens next.",
                },
            )
            raised += 1
        return raised

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def latest_batches(self) -> list[dict]:
        """Latest batch per model, with distribution and the highest-risk students."""
        from app.modules.person.models import Person
        from app.modules.student_record.models import Student

        models = (await self.session.execute(
            select(MlModel).order_by(MlModel.created_at.desc())
        )).scalars().all()
        out = []
        for m in models:
            last = (await self.session.execute(
                select(MlPrediction).where(MlPrediction.model_id == m.id)
                .order_by(MlPrediction.scored_at.desc()).limit(1)
            )).scalars().first()
            if last is None:
                continue
            rows = (await self.session.execute(
                select(MlPrediction, Student, Person)
                .join(Student, Student.id == MlPrediction.student_id)
                .join(Person, Person.id == Student.person_id)
                .where(MlPrediction.batch_id == last.batch_id)
                .order_by(MlPrediction.probability.desc())
            )).all()
            probs = [p.probability for p, _, _ in rows]
            bins = [0] * 5
            for p in probs:
                bins[min(4, int(p * 5))] += 1
            out.append({
                "modelId": str(m.id), "modelName": m.name, "targetKey": m.target_key,
                "batchId": str(last.batch_id),
                "scoredAt": last.scored_at.isoformat() if last.scored_at else None,
                "scored": len(rows),
                "meanProbability": round(sum(probs) / len(probs), 4) if probs else None,
                "distribution": [
                    {"band": f"{i*20}–{i*20+20}%", "count": bins[i]} for i in range(5)],
                "top": [{
                    "studentId": str(s.id), "studentRef": s.student_ref,
                    "studentName": f"{per.given_name} {per.family_name}",
                    "probability": p.probability, "factors": p.factors,
                    "link": f"/students/{s.id}",
                } for p, s, per in rows[:15]],
            })
        return out

    async def for_student(self, student_id: uuid.UUID) -> list[dict]:
        """Latest prediction per model for one student — the student-detail panel."""
        models = (await self.session.execute(select(MlModel))).scalars().all()
        out = []
        for m in models:
            p = (await self.session.execute(
                select(MlPrediction).where(
                    MlPrediction.model_id == m.id,
                    MlPrediction.student_id == student_id,
                ).order_by(MlPrediction.scored_at.desc()).limit(1)
            )).scalars().first()
            if p is None:
                continue
            target = TARGETS.get(m.target_key)
            out.append({
                "modelId": str(m.id), "modelName": m.name,
                "versionId": str(p.model_version_id),
                "outcome": target.outcome_label if target else m.target_key,
                "probability": p.probability, "factors": p.factors,
                "scoredAt": p.scored_at.isoformat() if p.scored_at else None,
                "note": "Advisory prediction beside the deterministic indicators — "
                        "association, not causation; a human decides.",
            })
        return out
