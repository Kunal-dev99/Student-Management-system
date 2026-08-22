"""Pattern Lab PL-6 — monitoring & manual-first retraining.

What must hold: matured predictions are compared against real outcomes; drift is measured
feature-by-feature against the frozen training matrix; the health verdict names its
reasons; and retraining produces a CANDIDATE that still has to walk governance — nothing
auto-promotes, ever.
"""
from __future__ import annotations

import pytest

from tests.integration.test_pattern_lab import ctx  # noqa: F401  (reuse the fixture)
from tests.integration.test_pattern_lab_governance import _second_admin, _t
from tests.integration.test_pattern_lab_predictions import _production_model


@pytest.mark.asyncio
async def test_monitoring_covers_actuals_drift_and_trend(ctx):
    c, h, _hv, sm = ctx
    m = await _production_model(c, h, sm)
    await c.post(f"/api/v1/pattern-lab/models/{m['id']}/score", headers=h)

    mon = (await c.get("/api/v1/pattern-lab/monitoring", headers=h)).json()
    entry = next(x for x in mon if x["modelId"] == m["id"])

    # Trend: one batch, whole cohort.
    assert len(entry["trend"]) == 1 and entry["trend"][0]["scored"] == 80

    # Actuals: the fixture's outcomes are all knowable, so every prediction has matured —
    # and the planted signal means matured AUC must be genuinely high.
    a = entry["actuals"]
    assert a["matured"] == 80 and a["judged"] is True
    assert a["aucOnMatured"] is not None and a["aucOnMatured"] > 0.7
    bands = {b["band"]: b for b in a["realizedByBand"]}
    assert sum(b["n"] for b in a["realizedByBand"]) == 80
    # Calibration in the wild: the top band's realised rate exceeds the bottom band's.
    populated = [b for b in a["realizedByBand"] if b["n"] >= 5]
    assert populated[-1]["realizedRate"] > populated[0]["realizedRate"]

    # Drift: every model feature measured against the frozen training matrix, with a band.
    assert {d["feature"] for d in entry["drift"]} == set(
        next(v for v in m["versions"] if v["status"] == "production")["featureKeys"])
    assert all(d["band"] in ("stable", "moderate", "major", None) for d in entry["drift"])

    # Health verdict names its reasons (possibly none) and recommends a review date.
    assert entry["health"] in ("ok", "watch", "review")
    assert entry["recommendedReviewAt"]
    if entry["health"] == "review":
        assert entry["reasons"]
    assert "never acts" in entry["note"]


@pytest.mark.asyncio
async def test_monitoring_lists_only_production_models(ctx):
    c, h, _hv, sm = ctx
    from tests.integration.test_pattern_lab_governance import _trained_candidate

    await _trained_candidate(c, h, name="Unmonitored candidate model")
    mon = (await c.get("/api/v1/pattern-lab/monitoring", headers=h)).json()
    assert all(x["modelName"] != "Unmonitored candidate model" for x in mon)


@pytest.mark.asyncio
async def test_retrain_produces_a_candidate_that_still_faces_governance(ctx):
    c, h, _hv, sm = ctx
    m = await _production_model(c, h, sm)

    r = await c.post(f"/api/v1/pattern-lab/models/{m['id']}/retrain", headers=h)
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["versionNo"] == 2
    assert "CANDIDATE" in run["note"] and "review and approval" in run["note"]

    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m2 = next(x for x in models if x["id"] == m["id"])
    v1 = next(v for v in m2["versions"] if v["versionNo"] == 1 and v["status"] == "production")
    assert v1 is not None                          # production untouched by retraining
    new_cands = [v for v in m2["versions"] if v["versionNo"] == 2 and v["status"] == "candidate"]
    assert len(new_cands) == 1                     # exactly one new candidate

    # And the new candidate cannot skip the queue: promote straight away is refused.
    r = await _t(c, new_cands[0]["id"], h, "promote", "skip governance")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_retrain_needs_ml_train(ctx):
    c, h, hv, sm = ctx
    m = await _production_model(c, h, sm)
    assert (await c.post(f"/api/v1/pattern-lab/models/{m['id']}/retrain",
                         headers=hv)).status_code == 403
