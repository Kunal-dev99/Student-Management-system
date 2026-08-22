"""Pattern Lab PL-5 — production predictions.

What must hold: only a governed production version can score; every prediction carries
per-student contributing factors; task raising obeys the institution settings, defaults to
OFF, and never duplicates an open task; the student endpoint serves the detail panel.
"""
from __future__ import annotations

import pytest

from tests.integration.test_pattern_lab import ctx  # noqa: F401  (reuse the fixture)
from tests.integration.test_pattern_lab_governance import (
    _second_admin,
    _t,
    _trained_candidate,
)


async def _production_model(c, h, sm, name="Prediction test model"):
    h2 = await _second_admin(sm, c)
    cand, _ = await _trained_candidate(c, h, name=name)
    await _t(c, cand["id"], h, "submit_review")
    await _t(c, cand["id"], h2, "approve", "ok")
    await _t(c, cand["id"], h2, "promote", "go live")
    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    return next(m for m in models if m["name"] == name)


@pytest.mark.asyncio
async def test_only_a_production_version_can_score(ctx):
    c, h, _hv, sm = ctx
    cand, _ = await _trained_candidate(c, h, name="Unpromoted model")
    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m = next(x for x in models if x["name"] == "Unpromoted model")
    r = await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)
    assert r.status_code == 409
    assert "no production version" in r.text
    assert "governance" in r.text            # the refusal teaches the rule


@pytest.mark.asyncio
async def test_scoring_writes_explained_predictions(ctx):
    c, h, _hv, sm = ctx
    m = await _production_model(c, h, sm)
    r = await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["scored"] == 80               # the whole active fixture cohort
    assert run["tasksRaised"] == 0           # task raising is OFF by default

    batches = (await c.get("/api/v1/pattern-lab/predictions", headers=h)).json()
    b = next(x for x in batches if x["modelId"] == m["id"])
    assert b["scored"] == 80
    assert sum(band["count"] for band in b["distribution"]) == 80
    top = b["top"][0]
    assert top["probability"] >= b["top"][-1]["probability"]     # ranked
    assert top["factors"], "every prediction must explain itself"
    f = top["factors"][0]
    assert {"feature", "label", "value", "deltaPp"} <= set(f)
    assert top["link"].startswith("/students/")

    # The riskiest students should be the planted unfunded group — the model's top factor
    # is funding, so their factor list must mention it.
    labels = " ".join(x["label"] for x in top["factors"])
    assert "Funding" in labels or "funding" in labels

    # Student-detail view serves the same prediction with the advisory note.
    sp = (await c.get(f"/api/v1/pattern-lab/students/{top['studentId']}/predictions",
                      headers=h)).json()
    assert sp and sp[0]["probability"] == top["probability"]
    assert "human decides" in sp[0]["note"]


@pytest.mark.asyncio
async def test_task_raising_obeys_settings_and_never_duplicates(ctx):
    c, h, _hv, sm = ctx
    m = await _production_model(c, h, sm)

    # Turn the institution setting on with a threshold the planted group clears.
    r = await c.put("/api/v1/settings/institution/pattern_lab.raise_tasks",
                    headers=h, json={"value": True})
    assert r.status_code == 200, r.text
    await c.put("/api/v1/settings/institution/pattern_lab.task_threshold",
                headers=h, json={"value": 0.5})

    run = (await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)).json()
    assert run["tasksRaised"] > 0, f"no tasks at threshold 0.5: {run}"

    # Tasks are assigned to the PGR Administrator role, so count them in the store
    # (the /tasks list is role-filtered and the fixture admin holds a different role).
    from sqlalchemy import select as _sel

    from app.modules.workflow.models import Task

    async with sm() as s:
        ml_tasks = [t for t in (await s.execute(_sel(Task))).scalars().all()
                    if "Review predicted risk" in t.title]
    assert len(ml_tasks) == run["tasksRaised"]
    assert "Prediction test model" in ml_tasks[0].title
    assert ml_tasks[0].assignee_role == "PGR Administrator"
    assert "human decides" in (ml_tasks[0].payload or {}).get("note", "")

    # Rescoring while those tasks are open must not duplicate them.
    run2 = (await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)).json()
    assert run2["tasksRaised"] == 0
    async with sm() as s:
        again = [t for t in (await s.execute(_sel(Task))).scalars().all()
                 if "Review predicted risk" in t.title]
    assert len(again) == len(ml_tasks)


@pytest.mark.asyncio
async def test_prediction_reads_require_ml_read(ctx):
    c, _h, hv, _sm = ctx
    assert (await c.get("/api/v1/pattern-lab/predictions", headers=hv)).status_code == 403


@pytest.mark.asyncio
async def test_prediction_history_is_append_only_and_traceable(ctx):
    """Two batches → two sets of rows; reads use the newest; every row names its version."""
    from sqlalchemy import func, select as _sel

    from app.modules.pattern_lab.models import MlPrediction

    c, h, _hv, sm = ctx
    m = await _production_model(c, h, sm)
    b1 = (await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)).json()
    b2 = (await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)).json()
    assert b1["batchId"] != b2["batchId"]

    async with sm() as s:
        total = (await s.execute(
            _sel(func.count()).select_from(MlPrediction)
        )).scalar_one()
    assert total == 160                       # 2 batches × 80, nothing overwritten

    batches = (await c.get("/api/v1/pattern-lab/predictions", headers=h)).json()
    b = next(x for x in batches if x["modelId"] == m["id"])
    assert b["batchId"] == b2["batchId"]      # reads follow the latest batch

    prod = next(v for v in m["versions"] if v["status"] == "production")
    sp = (await c.get(
        f"/api/v1/pattern-lab/students/{b['top'][0]['studentId']}/predictions",
        headers=h)).json()
    assert sp[0]["versionId"] == prod["id"]   # prediction → exact version, always
