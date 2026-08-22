"""Supervisor matching and the relationship graph (Phase 7, item R5).

The point of these tests is not that a ranking comes back — it is that the ranking is
**defensible**. Every assertion below is one a supervisor could raise in a meeting: "why was I
ranked below her?", "why wasn't I suggested at all?", "you know I'm already full, right?"
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.research.models import ResearchAward
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import ResearchArea, ResearchProject, Student
from app.modules.supervision.constants import SupervisorRole
from app.modules.supervision.models import SupervisorRelationship


@pytest_asyncio.fixture
async def ctx():
    """A small department: two supervisors in ML, one in medieval history, one at capacity."""
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False},
                              poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)

    ids: dict = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="PGR Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        ml = ResearchArea(name="Machine Learning", code="ML")
        hist = ResearchArea(name="Medieval History", code="HIST")
        s.add_all([ml, hist]); await s.flush()
        ids["ml"], ids["hist"] = ml.id, hist.id

        funder = FundingSource(name="EPSRC", funder_type="research_council")
        s.add(funder); await s.flush()
        award = ResearchAward(award_ref="EP/X/1", title="Trustworthy ML", funder_id=funder.id,
                              start_date=date(2024, 1, 1), end_date=date(2028, 1, 1))
        s.add(award); await s.flush()
        ids["award"], ids["funder"] = award.id, funder.id

        def person(g, f):
            p = Person(given_name=g, family_name=f, email=f"{g}.{f}@uni.ac.uk".lower())
            s.add(p)
            return p

        # Supervisors
        okonkwo = person("Ada", "Okonkwo")        # ML, 2 supervisees, 1 completed
        bell = person("Tom", "Bell")              # ML, 7 supervisees (nearly full)
        rossi = person("Elena", "Rossi")          # History, 1 supervisee
        crowe = person("Sam", "Crowe")            # ML, 8 supervisees — at capacity
        await s.flush()
        ids["okonkwo"], ids["bell"] = okonkwo.id, bell.id
        ids["rossi"], ids["crowe"] = rossi.id, crowe.id

        n = 0

        async def student(sup, area, topic, *, ended=False, funded=False):
            nonlocal n
            n += 1
            p = person("Stu", f"Dent{n}")
            await s.flush()
            st = Student(person_id=p.id, student_ref=f"PGR{n:04d}", research_area_id=area,
                         start_date=date(2025, 10, 1), expected_end_date=date(2028, 9, 30),
                         status=StudentStatus.active)
            s.add(st); await s.flush()
            s.add(ResearchProject(student_id=st.id, research_topic=topic,
                                  research_award_id=ids["award"] if funded else None))
            s.add(SupervisorRelationship(
                student_id=st.id, supervisor_person_id=sup, role=SupervisorRole.primary,
                valid_from=date(2025, 10, 1), valid_to=date(2026, 1, 1) if ended else None))
            if funded:
                s.add(FundingArrangement(
                    student_id=st.id, funding_source_id=ids["funder"],
                    research_award_id=ids["award"], funding_type=FundingType.research_council,
                    status=FundingStatus.active, valid_from=date(2025, 10, 1),
                    valid_to=None, stipend_amount=19000, currency="GBP"))
            await s.flush()
            return st.id

        ids["first"] = await student(okonkwo.id, ml.id,
                                     "Interpretable neural networks for medical imaging",
                                     funded=True)
        await student(okonkwo.id, ml.id, "Robustness of transformer language models")
        await student(okonkwo.id, ml.id, "Graph representation learning", ended=True)
        for i in range(7):
            await student(bell.id, ml.id, "Reinforcement learning for robotics")
        await student(rossi.id, hist.id, "Monastic charters in twelfth-century Burgundy")
        for i in range(8):
            await student(crowe.id, ml.id, "Neural architecture search")
        await s.commit()

    ids["sm"] = sm

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, ids
    app.dependency_overrides.clear()
    await eng.dispose()


# ----------------------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_area_specialists_outrank_everyone_else(ctx):
    c, h, ids = ctx
    r = await c.post("/api/v1/research/supervisor-suggestions", headers=h,
                     json={"researchAreaId": str(ids["ml"])})
    assert r.status_code == 200, r.text
    names = [s["personName"] for s in r.json()["suggestions"]]
    assert names[0] == "Ada Okonkwo"                     # ML + capacity + track record
    assert names.index("Elena Rossi") > names.index("Tom Bell")   # wrong area, ranked last


@pytest.mark.asyncio
async def test_every_point_is_attributed_to_a_named_reason(ctx):
    """The score must never be a bare number — a rejected supervisor is owed an explanation."""
    c, h, ids = ctx
    body = (await c.post("/api/v1/research/supervisor-suggestions", headers=h,
                         json={"researchAreaId": str(ids["ml"])})).json()
    top = body["suggestions"][0]
    assert top["score"] == sum(x["points"] for x in top["reasons"])
    factors = {x["factor"] for x in top["reasons"]}
    assert {"research area", "capacity", "track record"} <= factors
    assert "already supervises in Machine Learning" in str(top["reasons"])


@pytest.mark.asyncio
async def test_a_full_supervisor_is_shown_but_scored_down_not_hidden(ctx):
    """Hiding them would make the tool look wrong to anyone who knows the department."""
    c, h, ids = ctx
    body = (await c.post("/api/v1/research/supervisor-suggestions", headers=h,
                         json={"researchAreaId": str(ids["ml"])})).json()
    crowe = next(s for s in body["suggestions"] if s["personName"] == "Sam Crowe")
    assert crowe["atCapacity"] is True
    assert crowe["currentSupervisees"] == 8
    assert any(x["factor"] == "capacity" and x["points"] == 0 for x in crowe["reasons"])
    okonkwo = next(s for s in body["suggestions"] if s["personName"] == "Ada Okonkwo")
    assert okonkwo["score"] > crowe["score"]


@pytest.mark.asyncio
async def test_free_text_proposal_matches_on_topic_not_just_area(ctx):
    """A proposal with no area attached should still find the right person."""
    c, h, _ = ctx
    body = (await c.post("/api/v1/research/supervisor-suggestions", headers=h, json={
        "proposalText": "Interpretable neural networks applied to medical imaging diagnosis"
    })).json()
    top = body["suggestions"][0]
    assert top["personName"] == "Ada Okonkwo"
    overlap = next(x for x in top["reasons"] if x["factor"] == "topic overlap")
    assert "interpretable" in overlap["detail"] or "imaging" in overlap["detail"]


@pytest.mark.asyncio
async def test_no_criteria_returns_nothing_rather_than_an_arbitrary_ranking(ctx):
    c, h, _ = ctx
    body = (await c.post("/api/v1/research/supervisor-suggestions", headers=h, json={})).json()
    assert body["suggestions"] == []
    assert "Provide a research area" in body["note"]


@pytest.mark.asyncio
async def test_the_area_name_is_not_counted_twice_as_topic_overlap(ctx):
    """Searching "Machine Learning" must not award the area *and* score "machine, learning" as
    topic evidence — that is one signal counted twice, and it flattens the ranking between
    supervisors who genuinely differ in what they work on. Found on real cohort data."""
    c, h, ids = ctx
    body = (await c.post("/api/v1/research/supervisor-suggestions", headers=h,
                         json={"researchAreaId": str(ids["ml"])})).json()
    for s in body["suggestions"]:
        overlap = [x for x in s["reasons"] if x["factor"] == "topic overlap"]
        assert not overlap, f"{s['personName']} scored topic overlap from the area name alone"

    # But a proposal that shares real terms with their work still scores, even alongside an area.
    with_text = (await c.post("/api/v1/research/supervisor-suggestions", headers=h, json={
        "researchAreaId": str(ids["ml"]),
        "proposalText": "Interpretable models for medical imaging",
    })).json()
    top = with_text["suggestions"][0]
    assert top["personName"] == "Ada Okonkwo"
    assert any(x["factor"] == "topic overlap" for x in top["reasons"])


@pytest.mark.asyncio
async def test_stopwords_do_not_manufacture_a_match(ctx):
    """'A study of the research approach' shares only noise words with everything."""
    c, h, _ = ctx
    body = (await c.post("/api/v1/research/supervisor-suggestions", headers=h, json={
        "proposalText": "A novel study of the research methods for this new approach"
    })).json()
    assert all(not any(x["factor"] == "topic overlap" for x in s["reasons"])
               for s in body["suggestions"])


# ----------------------------------------------------------------------------------
# Relationship graph
# ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_connects_student_to_funder_through_the_chain(ctx):
    c, h, ids = ctx
    r = await c.get(f"/api/v1/research/graph?studentId={ids['first']}", headers=h)
    assert r.status_code == 200, r.text
    g = r.json()
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"student", "project", "supervisor", "award", "funder", "funding"} <= kinds

    labels = {e["label"] for e in g["edges"]}
    assert {"researches", "under", "funds", "provides", "awards"} <= labels
    assert any(e["label"] == "primary" for e in g["edges"])      # supervisor → student

    # Every edge must land on a node that exists, or the drawing breaks.
    node_ids = {n["id"] for n in g["nodes"]}
    for e in g["edges"]:
        assert e["source"] in node_ids and e["target"] in node_ids


@pytest.mark.asyncio
async def test_graph_does_not_repeat_an_edge_reachable_by_two_paths(ctx):
    c, h, ids = ctx
    g = (await c.get(f"/api/v1/research/graph?studentId={ids['first']}", headers=h)).json()
    keys = [(e["source"], e["target"], e["label"]) for e in g["edges"]]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_graph_is_bounded_so_a_whole_cohort_cannot_be_dumped(ctx):
    c, h, _ = ctx
    g = (await c.get("/api/v1/research/graph?limit=3", headers=h)).json()
    assert g["counts"]["students"] == 3


@pytest.mark.asyncio
async def test_a_supervisor_sees_only_their_own_students_in_the_graph(ctx):
    """The graph exposes funding amounts and supervision links, so it must obey row scoping —
    and an out-of-scope student must come back empty, not as someone else's data."""
    c, h, ids = ctx
    async with ids["sm"]() as s:
        perms = {p.code: p for p in (await s.execute(select(Permission))).scalars().all()}
        sup_role = Role(name="Supervisor")
        s.add(sup_role); await s.flush()
        await s.refresh(sup_role, ["permissions"])
        sup_role.permissions = [perms["student.read"]]
        u = User(email="rossi@t.com", password_hash=hash_password("pw"), is_active=True,
                 person_id=ids["rossi"])
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [sup_role]
        await s.commit()

    r = await c.post("/api/v1/auth/login", json={"email": "rossi@t.com", "password": "pw"})
    sh = {"Authorization": f"Bearer {r.json()['accessToken']}"}

    mine = (await c.get("/api/v1/research/graph", headers=sh)).json()
    assert mine["counts"]["students"] == 1          # Rossi supervises exactly one

    # Ada Okonkwo's student is not Rossi's to see.
    theirs = (await c.get(f"/api/v1/research/graph?studentId={ids['first']}", headers=sh)).json()
    assert theirs["nodes"] == []


@pytest.mark.asyncio
async def test_research_areas_are_discoverable(ctx):
    """`supervisor-suggestions` takes a researchAreaId, so callers need a way to find one."""
    c, h, _ = ctx
    r = await c.get("/api/v1/research-areas", headers=h)
    assert r.status_code == 200, r.text
    names = [a["name"] for a in r.json()]
    assert names == ["Machine Learning", "Medieval History"]      # sorted, not insertion order
    assert all(a["id"] and a["code"] for a in r.json())
