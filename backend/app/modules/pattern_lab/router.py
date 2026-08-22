"""Pattern Lab endpoints (PL-1 + PL-2).

Permissions: `ml.read` to see targets/datasets/findings, `ml.analyse` to build datasets and
run discovery. Training (`ml.train`) and promotion (`ml.approve`) arrive with PL-3/PL-4.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import NotFoundError
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.modules.pattern_lab.dataset import DatasetBuilder
from app.modules.pattern_lab.discovery import DiscoveryService
from app.modules.pattern_lab.models import MlDataset, MlFinding
from app.modules.pattern_lab.targets import TARGETS, target_out

router = APIRouter(prefix="/pattern-lab", tags=["pattern-lab"])


class BuildRequest(BaseModel):
    targetKey: str


def _dataset_out(ds: MlDataset, *, with_matrix: bool = False) -> dict:
    out = {
        "id": str(ds.id), "targetKey": ds.target_key, "name": ds.name,
        "version": ds.version, "status": ds.status,
        "recordsFound": ds.records_found, "eligible": ds.eligible,
        "positives": ds.positives, "negatives": ds.eligible - ds.positives,
        "sufficient": ds.sufficient, "quality": ds.quality,
        "createdAt": ds.created_at.isoformat() if ds.created_at else None,
    }
    if with_matrix:
        out["matrix"] = ds.matrix
    return out


def _finding_out(f: MlFinding) -> dict:
    return {
        "id": str(f.id), "datasetId": str(f.dataset_id), "featureKey": f.feature_key,
        "rank": f.rank, "statement": f.statement, "significant": f.significant,
        "pValue": f.p_value, "effect": f.effect, "evidence": f.evidence,
        "createdAt": f.created_at.isoformat() if f.created_at else None,
    }


async def _overview_models(session: AsyncSession) -> list[dict]:
    from app.modules.pattern_lab.models import MlModel, MlModelVersion

    models = (await session.execute(
        select(MlModel).order_by(MlModel.created_at.desc()).limit(10)
    )).scalars().all()
    out = []
    for m in models:
        best = (await session.execute(
            select(MlModelVersion).where(MlModelVersion.model_id == m.id)
            .order_by(MlModelVersion.created_at.desc())
        )).scalars().all()
        cand = next((v for v in best if v.status == "candidate"), None) or (best[0] if best else None)
        out.append({
            "id": str(m.id), "name": m.name, "targetKey": m.target_key,
            "status": cand.status if cand else "no versions",
            "algorithm": cand.algorithm if cand else None,
            "aucMean": (cand.metrics or {}).get("aucMean") if cand else None,
            "beatsBaseline": cand.beats_baseline if cand else False,
        })
    return out


@router.get("/overview", summary="Pattern Lab home: targets, data health, recent discoveries")
async def overview(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> dict:
    builder = DatasetBuilder(session)
    targets = []
    for key, t in TARGETS.items():
        targets.append({**target_out(t), "sufficiency": await builder.sufficiency(key)})

    datasets = (await session.execute(
        select(MlDataset).order_by(MlDataset.created_at.desc()).limit(10)
    )).scalars().all()
    recent = (await session.execute(
        select(MlFinding).where(MlFinding.significant.is_(True))
        .order_by(MlFinding.created_at.desc(), MlFinding.rank).limit(5)
    )).scalars().all()
    return {
        "targets": targets,
        "datasets": [_dataset_out(d) for d in datasets],
        "recentFindings": [_finding_out(f) for f in recent],
        "stages": {"discover": "available", "models": "available",
                   "predictions": "available", "monitoring": "available"},
        # PL-3 — the home screen's ACTIVE MODELS panel: best version per model.
        "models": await _overview_models(session),
    }


@router.get("/targets", summary="Governed analysis targets, with sufficiency")
async def targets(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    builder = DatasetBuilder(session)
    return [{**target_out(t), "sufficiency": await builder.sufficiency(k)}
            for k, t in TARGETS.items()]


@router.post("/datasets", status_code=201, summary="Build a versioned dataset for a target")
async def build_dataset(
    body: BuildRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("ml.analyse")),
) -> dict:
    ds = await DatasetBuilder(session).build(body.targetKey, principal.user_id)
    return _dataset_out(ds)


@router.get("/datasets", summary="Built datasets")
async def list_datasets(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    rows = (await session.execute(
        select(MlDataset).order_by(MlDataset.created_at.desc())
    )).scalars().all()
    return [_dataset_out(d) for d in rows]


@router.get("/datasets/{dataset_id}", summary="One dataset with its quality report")
async def get_dataset(
    dataset_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> dict:
    ds = await session.get(MlDataset, dataset_id)
    if ds is None:
        raise NotFoundError("Dataset not found")
    return _dataset_out(ds)


@router.post("/datasets/{dataset_id}/discover", summary="Run pattern discovery on a dataset")
async def discover(
    dataset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("ml.analyse")),
) -> dict:
    findings = await DiscoveryService(session).discover(dataset_id)
    return {"findings": [_finding_out(f) for f in findings],
            "significant": sum(1 for f in findings if f.significant)}


# ---------------------------------------------------------------------------
# PL-3 — training & evaluation
# ---------------------------------------------------------------------------

class TrainRequest(BaseModel):
    datasetId: uuid.UUID
    name: str | None = None


def _version_out(v, *, with_artifact_size: bool = False) -> dict:
    return {
        "id": str(v.id), "modelId": str(v.model_id), "versionNo": v.version_no,
        "algorithm": v.algorithm, "params": v.params, "datasetVersion": v.dataset_version,
        "featureKeys": v.feature_keys, "metrics": v.metrics,
        "beatsBaseline": v.beats_baseline, "status": v.status,
        "createdAt": v.created_at.isoformat() if v.created_at else None,
        **({"artifactBytes": len(v.artifact or b"")} if with_artifact_size else {}),
    }


@router.post("/train", summary="Run the bounded candidate search on a dataset")
async def train(
    body: TrainRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("ml.train")),
) -> dict:
    from app.modules.pattern_lab.training import TrainingService

    return await TrainingService(session).train(
        body.datasetId, name=body.name, user_id=principal.user_id)


@router.get("/models", summary="Models with their versions and latest run verdicts")
async def list_models(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    from app.modules.pattern_lab.models import MlModel, MlModelVersion, MlTrainingRun
    from app.modules.pattern_lab.training import sklearn_available

    models = (await session.execute(
        select(MlModel).order_by(MlModel.created_at.desc())
    )).scalars().all()
    out = []
    for m in models:
        versions = (await session.execute(
            select(MlModelVersion).where(MlModelVersion.model_id == m.id)
            .order_by(MlModelVersion.version_no.desc(), MlModelVersion.created_at.desc())
        )).scalars().all()
        runs = (await session.execute(
            select(MlTrainingRun).where(MlTrainingRun.model_id == m.id)
            .order_by(MlTrainingRun.created_at.desc()).limit(5)
        )).scalars().all()
        out.append({
            "id": str(m.id), "targetKey": m.target_key, "name": m.name,
            "description": m.description,
            "createdAt": m.created_at.isoformat() if m.created_at else None,
            "versions": [_version_out(v, with_artifact_size=True) for v in versions],
            "runs": [{
                "id": str(r.id), "datasetVersion": r.dataset_version, "status": r.status,
                "durationMs": r.duration_ms, "detail": r.detail,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            } for r in runs],
        })
    return out if out or sklearn_available() else out


# ---------------------------------------------------------------------------
# PL-4 — governance
# ---------------------------------------------------------------------------

class TransitionRequest(BaseModel):
    action: str                 # submit_review | approve | decline | promote | retire
    rationale: str | None = None


@router.post("/versions/{version_id}/transition",
             summary="Move a model version through governance")
async def transition_version(
    version_id: uuid.UUID,
    body: TransitionRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("ml.train")),
) -> dict:
    from app.modules.pattern_lab.registry import NEEDS_SEPARATION, GovernanceService

    # Submitting for review is the trainer's act (ml.train); every *decision* —
    # approve/decline/promote/retire — needs the heavier ml.approve permission.
    if body.action in NEEDS_SEPARATION | {"retire"} and not principal.has_permission("ml.approve"):
        from app.core.errors import AuthError

        raise AuthError("This decision requires the ml.approve permission")
    return await GovernanceService(session).transition(
        version_id, action=body.action, rationale=body.rationale,
        user_id=principal.user_id, user_email=principal.email)


@router.get("/versions/{version_id}/card", summary="Auto-generated model card")
async def model_card(
    version_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> dict:
    from app.modules.pattern_lab.registry import GovernanceService

    return await GovernanceService(session).model_card(version_id)


@router.get("/versions/{version_id}/lineage",
            summary="Dataset → features → run → version → predictions")
async def version_lineage(
    version_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> dict:
    from app.modules.pattern_lab.registry import GovernanceService

    return await GovernanceService(session).lineage(version_id)


# ---------------------------------------------------------------------------
# PL-5 — production predictions
# ---------------------------------------------------------------------------

@router.post("/models/{model_id}/score",
             summary="Batch-score the live cohort with the production version")
async def score_model(
    model_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("ml.train")),
) -> dict:
    from app.modules.pattern_lab.prediction import PredictionService

    return await PredictionService(session).score(model_id)


@router.get("/predictions", summary="Latest batch per model: distribution + highest risk")
async def predictions(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    from app.modules.pattern_lab.prediction import PredictionService

    return await PredictionService(session).latest_batches()


@router.get("/students/{student_id}/predictions",
            summary="Latest prediction per model for one student")
async def student_predictions(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    from app.modules.pattern_lab.prediction import PredictionService

    return await PredictionService(session).for_student(student_id)


# ---------------------------------------------------------------------------
# PL-6 — monitoring & retraining
# ---------------------------------------------------------------------------

@router.get("/monitoring", summary="Health, drift and performance-vs-actuals per production model")
async def monitoring(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    from app.modules.pattern_lab.monitoring import MonitoringService

    return await MonitoringService(session).overview()


@router.post("/models/{model_id}/retrain",
             summary="Retrain on a fresh dataset (new CANDIDATE; governance still applies)")
async def retrain(
    model_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("ml.train")),
) -> dict:
    from app.modules.pattern_lab.monitoring import MonitoringService

    return await MonitoringService(session).retrain(model_id, principal.user_id)


@router.get("/ml-availability", summary="Is the optional [ml] extra installed?")
async def ml_availability(
    _=Depends(require_permission("ml.read")),
) -> dict:
    from app.modules.pattern_lab.training import sklearn_available

    return {"available": sklearn_available(),
            "note": None if sklearn_available() else
            "Model training needs the optional ML extra: pip install scikit-learn."}


@router.get("/datasets/{dataset_id}/findings", summary="Findings for a dataset, ranked")
async def findings(
    dataset_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("ml.read")),
) -> list[dict]:
    rows = (await session.execute(
        select(MlFinding).where(MlFinding.dataset_id == dataset_id).order_by(MlFinding.rank)
    )).scalars().all()
    return [_finding_out(f) for f in rows]
