"""Pattern Lab PL-4 — governance.

The rules a contested model must survive on: only legal transitions, two different humans
between training and production, written rationale on every decision, one production
version per model, and no governance momentum for a model that lost to the baseline.
"""
from __future__ import annotations

import pytest

from tests.integration.test_pattern_lab import ctx  # noqa: F401  (reuse the fixture)
from app.core.security import hash_password
from app.modules.identity.models import Role, User


async def _second_admin(sm, c):
    """A second Institution Administrator — approver separation demands one."""
    from sqlalchemy import select as _sel
    async with sm() as s:
        role = (await s.execute(_sel(Role).where(
            Role.name == "Institution Administrator"))).scalar_one()
        u = User(email="b@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        await s.commit()
    r = await c.post("/api/v1/auth/login", json={"email": "b@t.com", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


async def _trained_candidate(c, h, name="Governance test model"):
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "progression_delay"})).json()
    await c.post("/api/v1/pattern-lab/train", headers=h,
                 json={"datasetId": ds["id"], "name": name})
    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m = next(x for x in models if x["name"] == name)
    cand = next(v for v in m["versions"] if v["status"] == "candidate")
    failed = next((v for v in m["versions"] if not v["beatsBaseline"]), None)
    return cand, failed


def _t(c, vid, headers, action, rationale=None):
    body = {"action": action}
    if rationale is not None:
        body["rationale"] = rationale
    return c.post(f"/api/v1/pattern-lab/versions/{vid}/transition",
                  headers=headers, json=body)


@pytest.mark.asyncio
async def test_lifecycle_walks_to_production_with_two_humans(ctx):
    c, h, _hv, sm = ctx
    h2 = await _second_admin(sm, c)
    cand, _ = await _trained_candidate(c, h)
    vid = cand["id"]

    r = await _t(c, vid, h, "submit_review")
    assert r.status_code == 200 and r.json()["status"] == "review"

    # The trainer cannot approve their own work.
    r = await _t(c, vid, h, "approve", "looks fine to me")
    assert r.status_code == 409
    assert "Approver separation" in r.text

    r = await _t(c, vid, h2, "approve", "AUC clears baseline; factors are plausible.")
    assert r.json()["status"] == "approved"
    r = await _t(c, vid, h2, "promote", "Approved for advisory use.")
    assert r.json()["status"] == "production"

    # The governance log tells the whole story, with both humans in it.
    log = r.json()["log"]
    assert [e["action"] for e in log] == ["submit_review", "approve", "promote"]
    assert log[0]["byEmail"] == "a@t.com" and log[1]["byEmail"] == "b@t.com"
    assert log[1]["rationale"].startswith("AUC clears baseline")


@pytest.mark.asyncio
async def test_decisions_require_rationale_and_legal_transitions(ctx):
    c, h, _hv, sm = ctx
    h2 = await _second_admin(sm, c)
    cand, _ = await _trained_candidate(c, h)
    vid = cand["id"]

    # Cannot approve straight from candidate — review is not skippable.
    r = await _t(c, vid, h2, "approve", "skip the queue")
    assert r.status_code == 409 and "review" in r.text

    await _t(c, vid, h, "submit_review")
    # A decision without rationale is refused.
    r = await _t(c, vid, h2, "decline")
    assert r.status_code in (400, 422) and "rationale" in r.text.lower()
    r = await _t(c, vid, h2, "decline", "Exposure effect only; no actionable signal.")
    assert r.json()["status"] == "declined"


@pytest.mark.asyncio
async def test_a_version_that_lost_to_the_baseline_cannot_enter_review(ctx):
    """The planted signal is strong enough that every candidate beats the baseline here,
    so the losing state is forced directly — the gate itself is what's under test."""
    import uuid as _uuid

    from sqlalchemy import select as _sel

    from app.modules.pattern_lab.models import MlModelVersion

    c, h, _hv, sm = ctx
    cand, _ = await _trained_candidate(c, h)
    async with sm() as s:
        v = (await s.execute(_sel(MlModelVersion).where(
            MlModelVersion.id == _uuid.UUID(cand["id"])))).scalar_one()
        v.beats_baseline = False
        await s.commit()

    r = await _t(c, cand["id"], h, "submit_review")
    assert r.status_code == 409
    assert "baseline" in r.text
    assert "governance momentum" in r.text


@pytest.mark.asyncio
async def test_promotion_retires_the_incumbent(ctx):
    c, h, _hv, sm = ctx
    h2 = await _second_admin(sm, c)
    cand, _ = await _trained_candidate(c, h)

    async def to_production(vid):
        await _t(c, vid, h, "submit_review")
        await _t(c, vid, h2, "approve", "ok")
        return await _t(c, vid, h2, "promote", "go live")

    assert (await to_production(cand["id"])).json()["status"] == "production"

    # Retrain -> version 2; promoting it must retire version 1.
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "progression_delay"})).json()
    await c.post("/api/v1/pattern-lab/train", headers=h,
                 json={"datasetId": ds["id"], "name": "Governance test model"})
    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m = next(x for x in models if x["name"] == "Governance test model")
    new_cand = next(v for v in m["versions"]
                    if v["status"] == "candidate" and v["versionNo"] == 2)
    r = await to_production(new_cand["id"])
    assert r.json()["status"] == "production"
    assert r.json()["retiredIncumbent"]                    # names what it replaced

    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m = next(x for x in models if x["name"] == "Governance test model")
    statuses = [v["status"] for v in m["versions"]]
    assert statuses.count("production") == 1               # never two in production
    assert "retired" in statuses


@pytest.mark.asyncio
async def test_deciding_needs_ml_approve_not_just_ml_train(ctx):
    """PGR-style staff can train and submit; only ml.approve holders can decide."""
    c, h, _hv, sm = ctx
    from app.modules.identity.models import Permission
    from sqlalchemy import select as _sel
    async with sm() as s:
        perms = {p.code: p for p in (await s.execute(_sel(Permission))).scalars().all()}
        trainer = Role(name="ML Trainer")
        s.add(trainer); await s.flush(); await s.refresh(trainer, ["permissions"])
        trainer.permissions = [perms["ml.read"], perms["ml.analyse"], perms["ml.train"]]
        u = User(email="t@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [trainer]
        await s.commit()
    r = await c.post("/api/v1/auth/login", json={"email": "t@t.com", "password": "pw"})
    ht = {"Authorization": f"Bearer {r.json()['accessToken']}"}

    cand, _ = await _trained_candidate(c, ht, name="Trainer-only model")
    assert (await _t(c, cand["id"], ht, "submit_review")).status_code == 200
    r = await _t(c, cand["id"], ht, "approve", "I trained it, I approve it")
    assert r.status_code in (401, 403)
    assert "ml.approve" in r.text


@pytest.mark.asyncio
async def test_model_card_is_generated_with_honest_limitations(ctx):
    c, h, _hv, sm = ctx
    cand, _ = await _trained_candidate(c, h)
    card = (await c.get(f"/api/v1/pattern-lab/versions/{cand['id']}/card",
                        headers=h)).json()
    assert card["purpose"]["question"]                     # from the governed target
    assert card["data"]["datasetVersion"] == cand["datasetVersion"]
    assert card["method"]["algorithm"] == cand["algorithm"]
    assert card["performance"]["aucMean"] == cand["metrics"]["aucMean"]
    lims = " ".join(card["limitations"])
    assert "association, not causation" in lims
    assert "Small dataset" in lims                         # n=80 in this fixture

    lineage = (await c.get(f"/api/v1/pattern-lab/versions/{cand['id']}/lineage",
                           headers=h)).json()
    kinds = [x["kind"] for x in lineage["chain"]]
    assert kinds == ["dataset", "features", "trainingRun", "version", "predictions"]
