"""Bounded candidate search + honest evaluation (PL-3, plan §4/§6).

What "AutoML" means at institutional scale: four model families × small sensible parameter
grids, stratified 5-fold cross-validation, calibration measured, and a **dummy baseline that
every candidate must beat to matter**. No FLAML/AutoGluon/Optuna — at n≈300–800 that
machinery buys noise, not accuracy, and the comparison table it produces is exactly what
this module produces with sklearn alone.

Honesty rules, enforced in code:
- The baseline (predict the class prior) is trained and scored identically to every
  candidate. A candidate "beats baseline" only if its mean CV AUC clears the baseline by
  BASELINE_MARGIN *and* its (mean − std) stays above 0.5 — a model that only sometimes
  beats coin-flipping does not get the badge.
- If NO candidate beats the baseline, the run verdict is **failed** and says so. A failed
  run still records everything — a documented failure is a result, not an embarrassment.
- Explainability is permutation importance (model-agnostic) computed on held-out data;
  every version stores its ranked feature contributions.

The `[ml]` extra (scikit-learn) is optional platform-wide: without it, training endpoints
return a clear message and everything else (discovery included) keeps working.
"""
from __future__ import annotations

import pickle
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.modules.pattern_lab.models import MlDataset, MlModel, MlModelVersion, MlTrainingRun
from app.modules.pattern_lab.targets import TARGETS

BASELINE_MARGIN = 0.05      # mean AUC must clear baseline by this much
CV_FOLDS = 5
MIN_COMPLETENESS = 0.5      # features emptier than this are dropped (and reported)


def sklearn_available() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def _candidates():
    """The bounded search space. Small grids on purpose — see module docstring."""
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    return [
        ("baseline_prior", DummyClassifier(strategy="prior"), {}),
        ("logistic_regression", LogisticRegression(max_iter=2000, class_weight="balanced"),
         {"C": [0.1, 1.0]}),
        ("random_forest", RandomForestClassifier(n_estimators=100, class_weight="balanced",
                                                 random_state=0),
         {"max_depth": [3, 6]}),
        ("gradient_boosting", GradientBoostingClassifier(random_state=0),
         {"max_depth": [2, 3], "n_estimators": [100]}),
    ]


class TrainingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def train(self, dataset_id: uuid.UUID, *, name: str | None,
                    user_id: uuid.UUID | None) -> dict:
        if not sklearn_available():
            raise ValidationAppError(
                "Model training needs the optional ML extra. Install it on the server with: "
                "pip install scikit-learn (see requirements.txt, Pattern Lab PL-3 section)."
            )
        ds = await self.session.get(MlDataset, dataset_id)
        if ds is None:
            raise NotFoundError("Dataset not found")
        if not ds.sufficient:
            raise ValidationAppError(
                "This dataset did not pass the sufficiency gate — a model trained on it "
                "would be noise with a version number."
            )

        import numpy as np
        from sklearn.impute import SimpleImputer
        from sklearn.inspection import permutation_importance
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            roc_auc_score,
        )
        from sklearn.model_selection import (
            GridSearchCV,
            StratifiedKFold,
            cross_val_predict,
            train_test_split,
        )
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        t0 = time.perf_counter()
        target = TARGETS[ds.target_key]

        # --- matrix → arrays; drop features below the completeness floor (and say so) ---
        all_keys = [f["key"] for f in ds.quality["activeFeatures"]]
        completeness = ds.quality.get("completeness", {})
        dropped = [{"key": k, "reason": f"only {completeness.get(k, 0):.0%} complete "
                                        f"(floor {MIN_COMPLETENESS:.0%})"}
                   for k in all_keys if completeness.get(k, 0) < MIN_COMPLETENESS]
        keys = [k for k in all_keys if completeness.get(k, 0) >= MIN_COMPLETENESS]
        X = np.array([[r["features"].get(k) if r["features"].get(k) is not None else np.nan
                       for k in keys] for r in ds.matrix], dtype=float)
        y = np.array([r["outcome"] for r in ds.matrix], dtype=int)

        model_name = name or f"{target.label} model"
        model = (await self.session.execute(
            select(MlModel).where(MlModel.name == model_name)
        )).scalar_one_or_none()
        if model is None:
            model = MlModel(target_key=ds.target_key, name=model_name,
                            description=target.question, created_by_user_id=user_id)
            self.session.add(model)
            await self.session.flush()
        elif model.target_key != ds.target_key:
            raise ValidationAppError(
                f"Model '{model_name}' belongs to target {model.target_key}; "
                "one model never mixes targets."
            )

        run = MlTrainingRun(model_id=model.id, dataset_id=ds.id,
                            dataset_version=ds.version, status="completed",
                            detail={}, started_by_user_id=user_id)
        self.session.add(run)
        await self.session.flush()

        next_no = ((await self.session.execute(
            select(func.max(MlModelVersion.version_no))
            .where(MlModelVersion.model_id == model.id)
        )).scalar_one() or 0) + 1

        cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=0)
        results, baseline_auc = [], 0.5

        for algo, estimator, grid in _candidates():
            pipe = Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("clf", estimator),
            ])
            param_grid = {f"clf__{k}": v for k, v in grid.items()}
            if param_grid:
                search = GridSearchCV(pipe, param_grid, cv=cv, scoring="roc_auc", n_jobs=1)
                search.fit(X, y)
                best, params = search.best_estimator_, {
                    k.removeprefix("clf__"): v for k, v in search.best_params_.items()}
            else:
                best, params = pipe.fit(X, y), {}

            # Out-of-fold probabilities → every metric is on data the model never fit.
            proba = cross_val_predict(best, X, y, cv=cv, method="predict_proba")[:, 1]
            fold_aucs = []
            for _, test_idx in cv.split(X, y):
                if len(set(y[test_idx])) > 1:
                    fold_aucs.append(roc_auc_score(y[test_idx], proba[test_idx]))
            auc_mean = float(np.mean(fold_aucs)) if fold_aucs else 0.5
            auc_std = float(np.std(fold_aucs)) if fold_aucs else 0.0
            preds = (proba >= 0.5).astype(int)
            tp = int(((preds == 1) & (y == 1)).sum())
            fp = int(((preds == 1) & (y == 0)).sum())
            fn = int(((preds == 0) & (y == 1)).sum())
            metrics = {
                "aucMean": round(auc_mean, 4), "aucStd": round(auc_std, 4),
                "averagePrecision": round(float(average_precision_score(y, proba)), 4),
                "brierScore": round(float(brier_score_loss(y, proba)), 4),
                "precisionAt50": round(tp / (tp + fp), 4) if (tp + fp) else None,
                "recallAt50": round(tp / (tp + fn), 4) if (tp + fn) else None,
                "cvFolds": CV_FOLDS, "n": int(len(y)), "positives": int(y.sum()),
            }

            if algo == "baseline_prior":
                baseline_auc = auc_mean
                results.append({"algorithm": algo, "params": params, "metrics": metrics,
                                "beatsBaseline": False, "isBaseline": True})
                continue

            beats = (auc_mean >= baseline_auc + BASELINE_MARGIN
                     and (auc_mean - auc_std) > 0.5)

            # Permutation importance on a held-out split — model-agnostic explainability.
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=0.25, stratify=y, random_state=0)
            fitted = best.fit(X_tr, y_tr)
            imp = permutation_importance(fitted, X_te, y_te, scoring="roc_auc",
                                         n_repeats=10, random_state=0)
            importance = sorted(
                ({"feature": keys[i],
                  "importance": round(float(imp.importances_mean[i]), 4)}
                 for i in range(len(keys))),
                key=lambda d: -abs(d["importance"]))
            metrics["permutationImportance"] = importance[:10]

            final = best.fit(X, y)   # refit on everything for the stored artifact
            version = MlModelVersion(
                model_id=model.id, training_run_id=run.id, version_no=next_no,
                algorithm=algo, params=params, dataset_version=ds.version,
                feature_keys=keys, metrics=metrics, beats_baseline=beats,
                status="trained", artifact=pickle.dumps(final),
            )
            self.session.add(version)
            results.append({"algorithm": algo, "params": params, "metrics": metrics,
                            "beatsBaseline": beats, "isBaseline": False})

        await self.session.flush()
        contenders = [r for r in results if r.get("beatsBaseline")]
        recommended = max(contenders, key=lambda r: r["metrics"]["aucMean"]) if contenders else None
        verdict = ("succeeded" if recommended else "failed")

        # The recommended version becomes the CANDIDATE; promotion beyond that is PL-4.
        if recommended:
            for v in (await self.session.execute(
                select(MlModelVersion).where(MlModelVersion.training_run_id == run.id)
            )).scalars().all():
                if v.algorithm == recommended["algorithm"]:
                    v.status = "candidate"

        run.duration_ms = int((time.perf_counter() - t0) * 1000)
        run.detail = {
            "verdict": verdict, "baselineAuc": round(baseline_auc, 4),
            "baselineMargin": BASELINE_MARGIN,
            "recommended": recommended["algorithm"] if recommended else None,
            "candidates": results, "droppedFeatures": dropped,
            "note": (None if recommended else
                     "No candidate beat the baseline by the required margin. This is a "
                     "result, not an error: the features available at the prediction point "
                     "do not predict this outcome in this data."),
        }
        await self.session.commit()
        await self.session.refresh(run)
        return {"runId": str(run.id), "modelId": str(model.id),
                "versionNo": next_no, "durationMs": run.duration_ms, **run.detail}
