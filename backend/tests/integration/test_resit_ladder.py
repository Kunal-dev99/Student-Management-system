"""ICR G1 (extension) — degrading resit-cap ladder.

The existing model supports a single flat resit cap (Assessment.resit_cap or
policy['resitCap']) that applies to every attempt >= 2. Some marks-and-standards regimes
want a DEGRADING cap: attempt 2 capped at 50, attempt 3 at 40, attempt 4+ at 30. This test
suite pins the ladder semantics plus the previously-untested policy fallback (the flat
default was silently ignored unless the assessment row had an explicit resit_cap set).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.student_record.constants import ProgrammeType
from app.modules.student_record.models import Programme
from app.modules.taught.constants import DEFAULT_GRADING_POLICY
from app.modules.taught.service import _effective_resit_cap


class _FakeAssessment:
    """Minimal stand-in with the two attributes _effective_resit_cap actually reads."""
    def __init__(self, resit_cap=None):
        self.resit_cap = resit_cap
        self.resit_allowed = True


# ---------- pure unit coverage of _effective_resit_cap ---------------------------------

def test_first_attempt_is_never_capped():
    """Attempt 1 is the raw first sit — no cap regardless of policy."""
    for attempt in [1, 0, -1]:
        assert _effective_resit_cap(DEFAULT_GRADING_POLICY, _FakeAssessment(), attempt) is None


def test_flat_policy_cap_applies_to_every_resit_when_no_ladder():
    """Backwards-compat: policy['resitCap'] (default 50) applies to attempts 2, 3, 4… when the
    ladder is not configured. This is the previously-broken fallback path."""
    for attempt in [2, 3, 4, 10]:
        assert _effective_resit_cap(DEFAULT_GRADING_POLICY, _FakeAssessment(), attempt) == Decimal("50")


def test_ladder_degrades_by_attempt_then_floors_at_last_value():
    """The ladder is indexed by (attempt - 2). Attempts beyond the list length re-use the LAST
    (harshest) value — the "we've been generous enough" floor."""
    policy = {**DEFAULT_GRADING_POLICY, "resitCapLadder": [50, 40, 30]}
    assert _effective_resit_cap(policy, _FakeAssessment(), 2) == Decimal("50")
    assert _effective_resit_cap(policy, _FakeAssessment(), 3) == Decimal("40")
    assert _effective_resit_cap(policy, _FakeAssessment(), 4) == Decimal("30")
    assert _effective_resit_cap(policy, _FakeAssessment(), 5) == Decimal("30")   # floored
    assert _effective_resit_cap(policy, _FakeAssessment(), 99) == Decimal("30")  # floored


def test_assessment_override_wins_over_policy():
    """A per-assessment cap is the most specific setting — it beats both the ladder and the flat
    policy cap. Lets Registry punish or relax a single component without touching the programme."""
    policy = {**DEFAULT_GRADING_POLICY, "resitCapLadder": [50, 40, 30], "resitCap": 45}
    a = _FakeAssessment(resit_cap=Decimal("35"))
    for attempt in [2, 3, 4, 10]:
        assert _effective_resit_cap(policy, a, attempt) == Decimal("35")


def test_no_cap_when_policy_and_assessment_are_both_empty():
    """When neither the assessment row, the ladder nor the flat cap is set, the resit is
    UNCAPPED — the honest fallback rather than silently applying 50."""
    policy = {k: v for k, v in DEFAULT_GRADING_POLICY.items() if k not in ("resitCap", "resitCapLadder")}
    assert _effective_resit_cap(policy, _FakeAssessment(), 2) is None


def test_ladder_wins_over_flat_policy_cap():
    """A programme configuring a ladder means it: the flat cap becomes irrelevant."""
    policy = {**DEFAULT_GRADING_POLICY, "resitCap": 99, "resitCapLadder": [50, 40]}
    assert _effective_resit_cap(policy, _FakeAssessment(), 2) == Decimal("50")
    assert _effective_resit_cap(policy, _FakeAssessment(), 3) == Decimal("40")


# ---------- integration: the ladder actually applies at record_result time -------------

@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        # Programme with a DEGRADING ladder — attempt 2 → 50, attempt 3 → 40, attempt 4+ → 30.
        prog = Programme(
            name="MSc Ladder", code="MSC-L", programme_type=ProgrammeType.taught,
            taught_total_credits=180,
            grading_policy={"resitCapLadder": [50, 40, 30]},
        )
        s.add(prog); await s.flush(); ids["programme"] = str(prog.id)
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
        yield c, h, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _post_ok(c, path, h, body, status=201):
    r = await c.post(path, headers=h, json=body)
    assert r.status_code == status, r.text
    return r.json()


@pytest.mark.asyncio
async def test_ladder_degrades_the_recorded_mark_across_attempts(ctx):
    """End-to-end proof: submitting three successive resits at 78 records them capped at 50, 40,
    30 per the ladder, and each row is flagged capped=True. First attempt (raw 30) is uncapped
    because attempt 1 always is."""
    c, h, ids = ctx
    pid = ids["programme"]

    m = await _post_ok(c, f"/api/v1/programmes/{pid}/modules", h, {
        "code": "M1", "title": "Module 1", "credits": 30, "level": 7, "isCore": False,
    })
    # Assessment carries no per-assessment override so the programme ladder rules.
    a = await _post_ok(c, f"/api/v1/taught-modules/{m['id']}/assessments", h, {
        "title": "Exam", "assessmentType": "exam", "weightPct": 100, "maxMark": 100,
        "passMark": 50, "resitAllowed": True, "resitCap": None,
    })
    sid = (await _post_ok(c, "/api/v1/students/enrol", h, {
        "person": {"givenName": "Ladder", "familyName": "Student"}, "programmeId": pid,
    }))["id"]
    enr = await _post_ok(c, f"/api/v1/students/{sid}/module-enrolments", h,
                         {"moduleId": m["id"], "academicYear": "2026/27"})

    # Attempt 1 — first sit, 30 raw. Uncapped.
    e = await _post_ok(c, f"/api/v1/module-enrolments/{enr['id']}/results", h,
                       {"assessmentId": a["id"], "mark": 30, "isResit": False})
    first = next(r for r in e["results"] if r["attemptNumber"] == 1)
    assert float(first["mark"]) == 30 and first["capped"] is False

    # Attempt 2 — resit at 78. Ladder[0] = 50 → recorded 50, capped True.
    e = await _post_ok(c, f"/api/v1/module-enrolments/{enr['id']}/results", h,
                       {"assessmentId": a["id"], "mark": 78, "isResit": True})
    second = next(r for r in e["results"] if r["attemptNumber"] == 2)
    assert float(second["mark"]) == 50 and second["capped"] is True

    # Attempt 3 — resit at 78. Ladder[1] = 40 → recorded 40, capped True.
    e = await _post_ok(c, f"/api/v1/module-enrolments/{enr['id']}/results", h,
                       {"assessmentId": a["id"], "mark": 78, "isResit": True})
    third = next(r for r in e["results"] if r["attemptNumber"] == 3)
    assert float(third["mark"]) == 40 and third["capped"] is True

    # Attempt 4 — resit at 78. Beyond ladder → floor at last value (30).
    e = await _post_ok(c, f"/api/v1/module-enrolments/{enr['id']}/results", h,
                       {"assessmentId": a["id"], "mark": 78, "isResit": True})
    fourth = next(r for r in e["results"] if r["attemptNumber"] == 4)
    assert float(fourth["mark"]) == 30 and fourth["capped"] is True
