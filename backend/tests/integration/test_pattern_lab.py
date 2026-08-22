"""Pattern Lab PL-1 + PL-2 (plan §7 success criteria, made executable).

The fixture *plants* an association — delayed students mostly lacked funding at the
prediction point — plus a deliberately uncorrelated noise feature. Discovery must find the
planted pattern, must NOT promote the noise, must exclude the leaky feature structurally,
and must refuse to analyse insufficient data. That is the whole product in four assertions.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition, ProgressionReview
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student
from app.modules.supervision.models import SupervisionMeeting


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False},
                              poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)

    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        admin = Role(name="Institution Administrator"); s.add(admin); await s.flush()
        await s.refresh(admin, ["permissions"]); admin.permissions = list(perms.values())
        viewer = Role(name="Viewer"); s.add(viewer); await s.flush()
        await s.refresh(viewer, ["permissions"]); viewer.permissions = [perms["student.read"]]
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [admin]
        v = User(email="v@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(v); await s.flush(); await s.refresh(v, ["roles"]); v.roles = [viewer]

        prog = Programme(name="PhD Engineering", code="PHD-ENG")
        s.add(prog); await s.flush()
        mdef = MilestoneDefinition(programme_id=prog.id, name="Confirmation Review",
                                   due_offset_days=180)
        s.add(mdef); await s.flush()

        # 80 students. Planted: 40 delayed (32 of them unfunded at the prediction point),
        # 40 on time (32 of them funded). Meetings alternate 1/3 by parity — pure noise.
        start, due = date(2024, 10, 1), date(2025, 4, 1)
        for i in range(80):
            delayed = i < 40
            funded_early = (i % 5 != 0) if not delayed else (i % 5 == 0)  # 32/8 vs 8/32
            p = Person(given_name="Pat", family_name=f"Lab{i}", email=f"pl{i}@uni.ac.uk")
            s.add(p); await s.flush()
            st = Student(person_id=p.id, student_ref=f"PL{i:04d}", programme_id=prog.id,
                         start_date=start, expected_end_date=date(2028, 9, 30),
                         status=StudentStatus.active)
            s.add(st); await s.flush()
            m = Milestone(student_id=st.id, milestone_definition_id=mdef.id,
                          due_date=due, status=MilestoneStatus.decided)
            s.add(m); await s.flush()
            decided = date(2025, 6, 15) if delayed else date(2025, 3, 20)
            s.add(ProgressionReview(
                milestone_id=m.id,
                decided_at=datetime(decided.year, decided.month, decided.day,
                                    tzinfo=timezone.utc)))
            # funded_early → an open arrangement from the start; late group → an arrangement
            # that began after the prediction point AND has since ended, so the funding
            # feature varies both at the training cutoff and at scoring time (today) —
            # PL-5 factor tests need today's features to vary on the decisive signal.
            s.add(FundingArrangement(
                student_id=st.id, funding_type=FundingType.university_scholarship,
                status=FundingStatus.active,
                valid_from=date(2024, 10, 1) if funded_early else date(2025, 5, 1),
                valid_to=None if funded_early else date(2025, 12, 1),
                stipend_amount=18000, currency="GBP"))
            for k in range(1 if i % 2 else 3):     # noise: uncorrelated with outcome
                s.add(SupervisionMeeting(student_id=st.id,
                                         met_on=date(2025, 1 + k, 5)))
            await s.flush()
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        r = await c.post("/api/v1/auth/login", json={"email": "v@t.com", "password": "pw"})
        hv = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, hv, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_targets_are_governed_and_gated(ctx):
    c, h, *_ = ctx
    body = (await c.get("/api/v1/pattern-lab/targets", headers=h)).json()
    by_key = {t["key"]: t for t in body}
    assert set(by_key) == {"progression_delay", "funding_continuity",
                           "completion_forecast", "applicant_outcome"}
    # Trainable target passes the gate on this fixture…
    assert by_key["progression_delay"]["sufficiency"]["sufficient"] is True
    assert by_key["progression_delay"]["sufficiency"]["positives"] == 40
    # …and the gated ones say exactly why they are locked.
    assert by_key["completion_forecast"]["sufficiency"]["sufficient"] is False
    assert "completion" in by_key["completion_forecast"]["sufficiency"]["reason"]
    assert "negative class" in by_key["applicant_outcome"]["sufficiency"]["reason"]


@pytest.mark.asyncio
async def test_dataset_is_reproducible_and_leak_free(ctx):
    c, h, *_ = ctx
    a = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                      json={"targetKey": "progression_delay"})).json()
    b = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                      json={"targetKey": "progression_delay"})).json()
    assert a["version"] == b["version"]           # same data → same version, always
    assert a["eligible"] == 80 and a["positives"] == 40

    # The leaky feature is excluded structurally, with its reason on the record.
    excluded = {e["key"]: e["reason"] for e in a["quality"]["excludedFeatures"]}
    assert "milestones_decided_total" in excluded
    assert "outcome" in excluded["milestones_decided_total"]
    active_keys = {f["key"] for f in a["quality"]["activeFeatures"]}
    assert "milestones_decided_total" not in active_keys
    assert "funded_at_cutoff" in active_keys      # fine for THIS target


@pytest.mark.asyncio
async def test_target_specific_exclusions_apply(ctx):
    c, h, *_ = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "funding_continuity"})).json()
    excluded = {e["key"] for e in ds["quality"]["excludedFeatures"]}
    # Near-tautological features for a funding-gap outcome are out, and say so.
    assert {"funded_at_cutoff", "funding_started_late"} <= excluded


@pytest.mark.asyncio
async def test_discovery_finds_the_planted_pattern_and_ignores_noise(ctx):
    c, h, *_ = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "progression_delay"})).json()
    r = await c.post(f"/api/v1/pattern-lab/datasets/{ds['id']}/discover", headers=h)
    assert r.status_code == 200, r.text
    findings = r.json()["findings"]

    by_key = {f["featureKey"]: f for f in findings}
    planted = by_key["funded_at_cutoff"]
    assert planted["significant"] is True
    assert planted["rank"] == 1                    # strongest pattern in the data
    assert planted["effect"] and planted["effect"] > 2.0
    assert "%" in planted["statement"]             # business language, not a coefficient
    assert planted["evidence"]["caution"].startswith("Association does not imply causation")

    noise = by_key.get("meetings_before")
    assert noise is None or noise["significant"] is False   # Bonferroni holds the line


@pytest.mark.asyncio
async def test_discovery_refuses_an_insufficient_dataset(ctx):
    c, h, *_ = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "funding_continuity"})).json()
    if ds["sufficient"]:
        pytest.skip("fixture funding target unexpectedly sufficient")
    r = await c.post(f"/api/v1/pattern-lab/datasets/{ds['id']}/discover", headers=h)
    assert r.status_code in (400, 422)
    assert "sufficiency" in r.text


@pytest.mark.asyncio
async def test_ml_permissions_gate_the_module(ctx):
    c, _, hv, _sm = ctx
    assert (await c.get("/api/v1/pattern-lab/overview", headers=hv)).status_code == 403
    assert (await c.post("/api/v1/pattern-lab/datasets", headers=hv,
                         json={"targetKey": "progression_delay"})).status_code == 403


@pytest.mark.asyncio
async def test_overview_composes_home_screen_data(ctx):
    c, h, *_ = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "progression_delay"})).json()
    await c.post(f"/api/v1/pattern-lab/datasets/{ds['id']}/discover", headers=h)
    body = (await c.get("/api/v1/pattern-lab/overview", headers=h)).json()
    assert len(body["targets"]) == 4
    assert body["datasets"]                       # the build shows up
    assert body["recentFindings"]                 # so does the discovery
    assert all(v == "available" for v in body["stages"].values())   # all six phases shipped


# ----------------------------------------------------------------------------------
# PL-3 — training & evaluation
# ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_training_learns_the_planted_signal_and_beats_the_baseline(ctx):
    """The fixture's outcome is strongly driven by funding-at-cutoff, so a competent
    candidate search must find a model with real out-of-fold AUC — and every claim it
    makes must be on held-out data."""
    c, h, *_ = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "progression_delay"})).json()
    r = await c.post("/api/v1/pattern-lab/train", headers=h,
                     json={"datasetId": ds["id"], "name": "Delay risk (test)"})
    assert r.status_code == 200, r.text
    run = r.json()

    assert run["verdict"] == "succeeded"
    assert run["recommended"] is not None
    baseline = next(x for x in run["candidates"] if x["isBaseline"])
    winner = next(x for x in run["candidates"] if x["algorithm"] == run["recommended"])
    assert winner["metrics"]["aucMean"] >= baseline["metrics"]["aucMean"] + 0.05
    assert winner["metrics"]["aucMean"] > 0.7          # the signal is genuinely strong

    # Explainability: the planted feature must top the permutation importance.
    top = winner["metrics"]["permutationImportance"][0]
    assert top["feature"] in ("funded_at_cutoff", "arrangements_before",
                              "funding_started_late")

    # Registry: versions recorded, recommended one promoted to candidate, artifact stored.
    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m = next(x for x in models if x["name"] == "Delay risk (test)")
    assert len(m["versions"]) == 3                     # three non-baseline candidates
    cand = [v for v in m["versions"] if v["status"] == "candidate"]
    assert len(cand) == 1 and cand[0]["algorithm"] == run["recommended"]
    assert cand[0]["artifactBytes"] > 0
    assert cand[0]["datasetVersion"] == ds["version"]  # full lineage, version to version


@pytest.mark.asyncio
async def test_training_on_noise_reports_failure_not_a_model(ctx):
    """Scramble the outcomes so no feature carries signal: the run must say FAILED and
    recommend nothing — a coin-flip with a version number is worse than no model."""
    import random

    from sqlalchemy import select as _select

    from app.modules.pattern_lab.models import MlDataset

    c, h, _hv, _sm = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "progression_delay"})).json()
    # Shuffle outcomes in place — same rates, zero association.
    async with _sm() as s:
        row = (await s.execute(
            _select(MlDataset).where(MlDataset.id == uuid.UUID(ds["id"])))).scalar_one()
        rng = random.Random(7)
        outcomes = [r["outcome"] for r in row.matrix]
        rng.shuffle(outcomes)
        row.matrix = [{**r, "outcome": o} for r, o in zip(row.matrix, outcomes)]
        await s.commit()

    r = await c.post("/api/v1/pattern-lab/train", headers=h,
                     json={"datasetId": ds["id"], "name": "Noise model (test)"})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["verdict"] == "failed"
    assert run["recommended"] is None
    assert "not an error" in run["note"]
    # Versions exist (the failure is documented) but none is a candidate.
    models = (await c.get("/api/v1/pattern-lab/models", headers=h)).json()
    m = next(x for x in models if x["name"] == "Noise model (test)")
    assert all(v["status"] == "trained" for v in m["versions"])


@pytest.mark.asyncio
async def test_training_requires_ml_train_and_a_sufficient_dataset(ctx):
    c, h, hv, _sm = ctx
    ds = (await c.post("/api/v1/pattern-lab/datasets", headers=h,
                       json={"targetKey": "funding_continuity"})).json()
    assert (await c.post("/api/v1/pattern-lab/train", headers=hv,
                         json={"datasetId": ds["id"]})).status_code == 403
    if not ds["sufficient"]:
        r = await c.post("/api/v1/pattern-lab/train", headers=h,
                         json={"datasetId": ds["id"]})
        assert r.status_code in (400, 422)
        assert "sufficiency" in r.text
