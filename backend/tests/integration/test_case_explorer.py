"""ICR G6 — comparable case explorer no longer returns identical scores.

The demo hit "scores all identical" because candidate feature vectors were synthesised from Task
rows with study_mode / programme / funding hard-coded to None, so only case_class ever matched.
Candidates are now built from real students, so structural similarity actually varies.
"""
from __future__ import annotations

from datetime import date

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
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]

        phd = Programme(name="PhD", code="PHD"); msc = Programme(name="MSc", code="MSC")
        s.add_all([phd, msc]); await s.flush()

        # Three deliberately different students so structural similarity must differ.
        def mk(ref, prog, mode, status):
            p = Person(given_name=ref, family_name="X"); s.add(p)
            return p, prog, mode, status
        specs = [
            ("A", phd, StudyMode.part_time, StudentStatus.active),    # closest to the subject
            ("B", phd, StudyMode.full_time, StudentStatus.active),    # differs on mode
            ("C", msc, StudyMode.full_time, StudentStatus.registered),  # differs on mode+prog+stage
        ]
        made = [mk(*sp) for sp in specs]
        await s.flush()
        funded_student = None
        for (p, prog, mode, status) in made:
            st = Student(person_id=p.id, student_ref=f"PGR-{p.given_name}", programme_id=prog.id,
                         study_mode=mode, status=status, start_date=date(2026, 1, 1))
            s.add(st); await s.flush()
            if p.given_name == "A":
                funded_student = st
        # Give the closest student active funding (subject has funding=true).
        s.add(FundingArrangement(student_id=funded_student.id, funding_type=FundingType.research_council,
                                 valid_from=date(2026, 1, 1), status=FundingStatus.active))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_similar_case_scores_vary(ctx):
    c, h = ctx
    r = await c.post("/api/v1/intelligence/cases/similar", headers=h, json={
        "case_class": "extension",
        "subject": {"case_class": "extension", "study_mode": "part_time", "stage": "active",
                    "has_active_funding": True, "supervision_overdue": True},
        "limit": 8,
    })
    assert r.status_code == 200, r.text
    scores = [cand["score"] for cand in r.json()["candidates"]]
    assert len(scores) == 3
    # The old bug produced one identical score for everyone; now they differ.
    assert len(set(scores)) > 1
    # The part-time, funded, active PhD student is the closest match.
    top = r.json()["candidates"][0]
    assert top["features"]["study_mode"] == "part_time"
    assert scores == sorted(scores, reverse=True)
