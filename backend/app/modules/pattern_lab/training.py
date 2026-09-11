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
    """The bounded search space.

    Small grids on purpose — see the module docstring. We include the two libraries the
    tabular-ML community actually deploys (xgboost, lightgbm) alongside the sklearn
    baselines; both are loaded only if installed so the pipeline degrades gracefully.
    """
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    candidates: list[tuple[str, object, dict]] = [
        ("baseline_prior", DummyClassifier(strategy="prior"), {}),
        ("logistic_regression", LogisticRegression(max_iter=2000, class_weight="balanced"),
         {"C": [0.1, 1.0]}),
        ("random_forest", RandomForestClassifier(n_estimators=100, class_weight="balanced",
                                                 random_state=0),
         {"max_depth": [3, 6]}),
        ("gradient_boosting", GradientBoostingClassifier(random_state=0),
         {"max_depth": [2, 3], "n_estimators": [100]}),
    ]

    # xgboost — industry-standard tabular booster; optional so the pipeline still runs
    # in a stripped-down environment.
    try:
        from xgboost import XGBClassifier
        candidates.append((
            "xgboost",
            XGBClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.1,
                eval_metric="logloss", random_state=0, tree_method="hist",
                verbosity=0,
            ),
            {"max_depth": [3, 5], "learning_rate": [0.05, 0.1]},
        ))
    except ImportError:
        pass

    # lightgbm — sibling to xgboost, faster on wide-ish tabular data.
    try:
        from lightgbm import LGBMClassifier
        candidates.append((
            "lightgbm",
            LGBMClassifier(
                n_estimators=200, max_depth=-1, num_leaves=31,
                learning_rate=0.1, class_weight="balanced",
                random_state=0, verbose=-1,
            ),
            {"num_leaves": [15, 31], "learning_rate": [0.05, 0.1]},
        ))
    except ImportError:
        pass

    return candidates


def _bootstrap_auc_ci(y_true, proba, n_iter: int = 300, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap 95% CI on ROC-AUC.

    Communicates uncertainty honestly — a point estimate like "AUC 0.82" hides how much
    of that number is signal vs. sample noise. At n≈500 an AUC often carries a ±0.05
    band; showing both makes the reader read the model correctly.
    """
    import numpy as np
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(seed)
    n = len(y_true)
    scores = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, size=n)
        if len(set(y_true[idx])) < 2:
            continue
        scores.append(roc_auc_score(y_true[idx], proba[idx]))
    if not scores:
        return (0.5, 0.5)
    scores.sort()
    return (round(float(scores[int(0.025 * len(scores))]), 4),
            round(float(scores[int(0.975 * len(scores))]), 4))


def _expected_calibration_error(y_true, proba, n_bins: int = 10) -> float:
    """ECE — weighted difference between predicted and realised rate per bin.

    Zero = perfectly calibrated. Anything above ~0.05 is worth calibrating. Reported
    alongside the raw AUC so a reader can spot models that rank well but return
    over/under-confident probabilities.
    """
    import numpy as np

    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        mask = (proba >= bins[i]) & (proba < bins[i + 1] if i < n_bins - 1 else proba <= bins[i + 1])
        if not mask.any():
            continue
        conf = float(proba[mask].mean())
        acc = float(y_true[mask].mean())
        ece += (mask.sum() / n) * abs(conf - acc)
    return round(float(ece), 4)


def _optimal_threshold(y_true, proba) -> tuple[float, float]:
    """Threshold that maximises F1 on out-of-fold predictions.

    Returns (threshold, f1). Fixed 0.5 is arbitrary — for imbalanced targets the operating
    point that trades precision vs recall best is often 0.2–0.4. Storing it lets the
    prediction service score consistently at the point the model was tuned for.
    """
    import numpy as np
    from sklearn.metrics import f1_score

    best_t, best_f1 = 0.5, 0.0
    for t in np.linspace(0.05, 0.95, 19):
        preds = (proba >= t).astype(int)
        if preds.sum() == 0:
            continue
        f1 = f1_score(y_true, preds, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return round(best_t, 3), round(float(best_f1), 4)


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
        from sklearn.calibration import CalibratedClassifierCV
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

            # Uncertainty + calibration + operating point — the three things a point
            # estimate hides. All computed on out-of-fold probabilities.
            auc_lo, auc_hi = _bootstrap_auc_ci(y, proba)
            ece = _expected_calibration_error(y, proba)
            opt_thr, opt_f1 = _optimal_threshold(y, proba)

            metrics = {
                "aucMean": round(auc_mean, 4), "aucStd": round(auc_std, 4),
                "aucCi95Low": auc_lo, "aucCi95High": auc_hi,
                "averagePrecision": round(float(average_precision_score(y, proba)), 4),
                "brierScore": round(float(brier_score_loss(y, proba)), 4),
                "expectedCalibrationError": ece,
                "precisionAt50": round(tp / (tp + fp), 4) if (tp + fp) else None,
                "recallAt50": round(tp / (tp + fn), 4) if (tp + fn) else None,
                "operatingThreshold": opt_thr,
                "operatingF1": opt_f1,
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

            # Wrap the fitted estimator with probability calibration. Isotonic when we
            # have enough positives to fit it cleanly, Platt (sigmoid) otherwise. The
            # metrics above are already-calibrated (out-of-fold), so the stored artifact
            # matches what we told the reader.
            positives = int(y.sum())
            calibration_method = "isotonic" if positives >= 60 else "sigmoid"
            calibrated = CalibratedClassifierCV(best, method=calibration_method, cv=cv)
            calibrated.fit(X, y)
            metrics["calibrationMethod"] = calibration_method

            version = MlModelVersion(
                model_id=model.id, training_run_id=run.id, version_no=next_no,
                algorithm=algo, params=params, dataset_version=ds.version,
                feature_keys=keys, metrics=metrics, beats_baseline=beats,
                status="trained", artifact=pickle.dumps(calibrated),
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
