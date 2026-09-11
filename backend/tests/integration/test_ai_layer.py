"""AI-as-a-layer proof: the model is off, and every feature still works.

The one test at the bottom is the whole point of the architecture — with `MockProvider`
selected (no API key configured), the weekly review queue endpoint still returns picks
sorted by the deterministic risk score, and every result is marked `source: "fallback"`
so the UI can style it appropriately.
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai import classify as classify_mod
from app.ai import narrate as narrate_mod
from app.ai import rank as rank_mod
from app.ai import read as read_mod
from app.ai.classify import classify
from app.ai.narrate import narrate
from app.ai.rank import rank
from app.ai.read import read
from app.ai.types import Candidate, Evidence
from app.core.llm import provider as provider_mod


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch):
    """Every test in this file runs with the model turned off.

    The whole point of the layer is to prove features still work without a live model.
    `_force_mock_provider` is autouse so an accidentally-live key doesn't invalidate the
    proof.
    """
    monkeypatch.setattr(provider_mod, "get_provider", lambda **_: provider_mod.MockProvider())
    # Every module imported `get_provider` at import time — repoint each caller.
    from app.ai import client as ai_client
    from app.modules.reviews import router as reviews_router
    monkeypatch.setattr(ai_client, "get_provider", lambda **_: provider_mod.MockProvider())
    monkeypatch.setattr(reviews_router, "provider_is_live", lambda: False)
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student

from pydantic import BaseModel


# ------------------------------------------------------------- unit tests: shapes

@pytest.mark.asyncio
async def test_rank_falls_back_to_score_order_when_model_is_off():
    candidates = [
        Candidate(id="s1", label="Student One", score=90.0, facts={"reasons": ["overdue"]}),
        Candidate(id="s2", label="Student Two", score=30.0, facts={"reasons": ["no funding"]}),
        Candidate(id="s3", label="Student Three", score=60.0, facts={"reasons": ["nearing end"]}),
    ]
    result = await rank(question="who first?", candidates=candidates, top_n=2)
    assert result.provenance.source == "fallback"
    assert [p.id for p in result.picks] == ["s1", "s3"]  # top two by score
    # Reasons come from the rule-based reason builder, not from a model.
    assert "overdue" in result.picks[0].reasoning


@pytest.mark.asyncio
async def test_rank_with_no_candidates_returns_empty_gracefully():
    result = await rank(question="q", candidates=[], top_n=5)
    assert result.picks == []
    assert result.provenance.source == "fallback"


class NoteFields(BaseModel):
    date: str | None = None
    agenda: str | None = None
    actions: list[str] | None = None


@pytest.mark.asyncio
async def test_read_falls_back_to_needs_manual_when_model_is_off():
    result = await read(text="Some meeting notes about the thesis chapter.", schema=NoteFields)
    assert result.provenance.source == "fallback"
    assert result.needs_manual is True
    assert set(result.fields.keys()) == {"date", "agenda", "actions"}


@pytest.mark.asyncio
async def test_classify_falls_back_to_keyword_rules():
    result = await classify(
        text="the student has missed two deadlines and is not responding",
        labels=["on_track", "at_risk", "blocked", "stalled"],
        keyword_rules={
            "at_risk": ["missed", "overdue"],
            "stalled": ["not responding"],
        },
        fallback_label="on_track",
    )
    assert result.provenance.source == "fallback"
    # Keyword rules are checked in dict order — "at_risk" wins first.
    assert result.label == "at_risk"


@pytest.mark.asyncio
async def test_narrate_falls_back_to_template_when_model_is_off():
    result = await narrate(
        evidence=Evidence(figures={"count": "42", "pct": "12%"}),
        question="How are we doing?",
        fallback_template="We have {count} active items ({pct} of target).",
    )
    assert result.provenance.source == "fallback"
    assert result.body == "We have 42 active items (12% of target)."


# ------------------------------------------------------------- end-to-end feature

@pytest_asyncio.fixture
async def client():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perm = Permission(code="student.read"); s.add(perm); await s.flush()
        role = Role(name="Reviewer"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [perm]
        user = User(email="r@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        pa = Person(given_name="Alex", family_name="Adams")
        pb = Person(given_name="Blair", family_name="Bell")
        pc = Person(given_name="Cass", family_name="Carr")
        pd = Person(given_name="Dee", family_name="Dixon")
        s.add_all([pa, pb, pc, pd]); await s.flush()

        # Alex — overdue milestones (score ~50), no funding (+20) = 70
        sa = Student(person_id=pa.id, student_ref="A1", start_date=date(2022, 1, 1),
                     study_mode=StudyMode.full_time, status=StudentStatus.registered)
        # Blair — funded, no issues → NOT in queue
        sb = Student(person_id=pb.id, student_ref="B1", start_date=date(2023, 1, 1),
                     study_mode=StudyMode.full_time, status=StudentStatus.registered)
        # Cass — past expected end (+25), no funding (+20) = 45
        sc = Student(person_id=pc.id, student_ref="C1", start_date=date(2020, 1, 1),
                     study_mode=StudyMode.full_time, status=StudentStatus.active,
                     expected_end_date=date(2023, 1, 1))
        # Dee — one overdue milestone (45), no funding (+20) = 65
        sd = Student(person_id=pd.id, student_ref="D1", start_date=date(2022, 1, 1),
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add_all([sa, sb, sc, sd]); await s.flush()

        s.add(FundingArrangement(
            student_id=sb.id, funding_type=FundingType.research_council,
            valid_from=date(2023, 1, 1), valid_to=None, status=FundingStatus.active,
        ))
        # Milestones hang off a definition; make a stub programme + definition so the FK holds.
        prog = Programme(name="Test PhD", code="TEST"); s.add(prog); await s.flush()
        mdef = MilestoneDefinition(programme_id=prog.id, name="Any milestone")
        s.add(mdef); await s.flush()
        s.add(Milestone(student_id=sa.id, milestone_definition_id=mdef.id,
                        status=MilestoneStatus.overdue, due_date=date(2024, 1, 1)))
        s.add(Milestone(student_id=sa.id, milestone_definition_id=mdef.id,
                        status=MilestoneStatus.overdue, due_date=date(2024, 6, 1)))
        s.add(Milestone(student_id=sd.id, milestone_definition_id=mdef.id,
                        status=MilestoneStatus.overdue, due_date=date(2025, 1, 1)))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "r@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_weekly_queue_works_with_model_off(client):
    """The whole point of the layer: turn the model off, the feature still works."""
    payload = (await client.get("/api/v1/reviews/weekly?top_n=3")).json()

    # Every response is provenance-tagged so the UI can label it.
    assert payload["provenance"]["source"] == "fallback"
    assert payload["modelLive"] is False

    # Three deterministic candidates emerged (Alex, Dee, Cass — Blair is fine).
    refs = {c["student_ref"] for c in payload["candidates"]}
    assert refs == {"A1", "C1", "D1"}

    # Alex has the highest score (two overdue milestones + no funding).
    assert payload["candidates"][0]["student_ref"] == "A1"

    # Top-3 picks are in the same deterministic order the candidate table is in.
    picked_refs = []
    by_id = {c["student_id"]: c["student_ref"] for c in payload["candidates"]}
    for pick in payload["picks"]:
        picked_refs.append(by_id[pick["id"]])
        # Every pick has non-empty rule-based reasoning.
        assert pick["reasoning"]
    assert picked_refs == ["A1", "D1", "C1"]
