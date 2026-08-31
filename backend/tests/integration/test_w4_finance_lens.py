"""W4 — Finance lens on the funding-integrity screen.

The Finance-lens report answers a cashflow question, not a compliance one: what did we schedule
this window, what got paid, what is stuck (held or overdue-approved), and where has reconciliation
drifted (paid without a Finance reference).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
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
from app.modules.funding.constants import FundingStatus, FundingType, PaymentStatus
from app.modules.funding.models import FundingArrangement, StipendPayment
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://",
                              connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        user = User(email="fin@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "fin@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _seed_cohort(sm) -> None:
    """Two students, mixed statuses across held / overdue / paid-reconciled / paid-drifted."""
    today = date.today()
    async with sm() as s:
        prog = Programme(name="PhD", code="PHD-W4"); s.add(prog); await s.flush()
        results = []
        for i, (given, ftype) in enumerate([
            ("Alice", FundingType.research_council),
            ("Bob", FundingType.scholarship),
        ]):
            per = Person(given_name=given, family_name=f"F{i}", email=f"{given.lower()}@t.com")
            s.add(per); await s.flush()
            stu = Student(person_id=per.id, student_ref=f"W4-{i}",
                          programme_id=prog.id, start_date=today - timedelta(days=180),
                          status=StudentStatus.active)
            s.add(stu); await s.flush()
            arr = FundingArrangement(
                student_id=stu.id, funding_type=ftype,
                stipend_amount=Decimal("18000"), currency="GBP",
                valid_from=today - timedelta(days=180), status=FundingStatus.active,
            )
            s.add(arr); await s.flush()
            results.append((stu, arr))

        (alice, alice_arr), (bob, bob_arr) = results

        # Alice — one HELD (Finance rejected), one PAID with finance ref (clean).
        s.add(StipendPayment(
            student_id=alice.id, arrangement_id=alice_arr.id, sequence=1,
            due_date=today, amount=Decimal("1500"), currency="GBP",
            status=PaymentStatus.held, note="Finance rejected: cost centre closed",
        ))
        s.add(StipendPayment(
            student_id=alice.id, arrangement_id=alice_arr.id, sequence=2,
            due_date=today - timedelta(days=30), amount=Decimal("1500"), currency="GBP",
            status=PaymentStatus.paid, paid_on=today - timedelta(days=28),
            finance_reference="FIN-OK-1",
        ))
        # Bob — one OVERDUE approved, one PAID without finance ref (drift).
        s.add(StipendPayment(
            student_id=bob.id, arrangement_id=bob_arr.id, sequence=1,
            due_date=today - timedelta(days=10), amount=Decimal("2000"), currency="GBP",
            status=PaymentStatus.approved,
        ))
        s.add(StipendPayment(
            student_id=bob.id, arrangement_id=bob_arr.id, sequence=2,
            due_date=today - timedelta(days=40), amount=Decimal("2000"), currency="GBP",
            status=PaymentStatus.paid, paid_on=today - timedelta(days=38),
            finance_reference=None,
        ))
        await s.commit()


@pytest.mark.asyncio
async def test_finance_lens_surfaces_held_overdue_and_unreconciled(ctx):
    c, h, sm = ctx
    await _seed_cohort(sm)

    # Wide window so every seeded payment lands in the totals bucket too.
    today = date.today()
    r = await c.get(
        "/api/v1/reports/funding-cashflow"
        f"?windowFrom={(today - timedelta(days=60)).isoformat()}"
        f"&windowTo={(today + timedelta(days=60)).isoformat()}",
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["counts"]["held"] == 1
    assert body["counts"]["overdueApproved"] == 1
    assert body["counts"]["paidWithoutFinanceReference"] == 1

    held = body["held"][0]
    assert held["personName"] == "Alice F0"
    assert "Finance rejected" in (held["note"] or "")
    assert Decimal(held["amount"]) == Decimal("1500")

    ov = body["overdueApproved"][0]
    assert ov["personName"] == "Bob F1"
    assert ov["daysOverdue"] == 10

    dr = body["paidWithoutFinanceReference"][0]
    assert dr["personName"] == "Bob F1"

    # Totals-in-window: 1 held + 1 approved + 2 paid = 4 payments; only paid counts as "paid".
    assert body["paymentsInWindow"] == 4
    # Alice paid 1500 + Bob paid 2000 = 3500
    assert Decimal(body["totals"]["paid"]) == Decimal("3500")
    assert Decimal(body["totals"]["held"]) == Decimal("1500")
    assert Decimal(body["totals"]["approved"]) == Decimal("2000")

    # Breakdown by funding type — both types appear, and paid/outstanding split is right.
    by_type = {row["fundingType"]: row for row in body["byFundingType"]}
    assert Decimal(by_type["research_council"]["paid"]) == Decimal("1500")
    assert Decimal(by_type["research_council"]["outstanding"]) == Decimal("1500")   # the held one
    assert Decimal(by_type["scholarship"]["paid"]) == Decimal("2000")
    assert Decimal(by_type["scholarship"]["outstanding"]) == Decimal("2000")        # the overdue-approved one


@pytest.mark.asyncio
async def test_finance_lens_window_default_is_current_quarter_ish(ctx):
    """No window params: totals bucket only counts payments due in the default window."""
    c, h, sm = ctx
    await _seed_cohort(sm)
    r = await c.get("/api/v1/reports/funding-cashflow", headers=h)
    assert r.status_code == 200
    body = r.json()
    # Default window starts at the first of the current month, so anything dated last month
    # is OUT of the totals — but held/overdue/unreconciled lists ignore the window.
    assert body["counts"]["held"] == 1
    assert body["counts"]["overdueApproved"] == 1
    # The two payments dated 30/40 days ago are before the window; only Alice's held (today)
    # and Bob's overdue (10 days ago — may be in window or out depending on the day of the
    # month the test runs). Assert only what is deterministic: paymentsInWindow >= 1.
    assert body["paymentsInWindow"] >= 1


@pytest.mark.asyncio
async def test_finance_lens_requires_funding_permission(ctx):
    """Without funding.read the report is refused, like every other funding surface."""
    from app.modules.identity.models import Permission, Role, User
    c, h, sm = ctx
    # New user with only reporting.read (no funding.read)
    async with sm() as s:
        p = (await s.execute(
            __import__("sqlalchemy").select(Permission).where(Permission.code == "reporting.read")
        )).scalar_one()
        role = Role(name="Analyst"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [p]
        u = User(email="analyst@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        await s.commit()

    r = await c.post("/api/v1/auth/login", json={"email": "analyst@t.com", "password": "pw"})
    h2 = {"Authorization": f"Bearer {r.json()['accessToken']}"}
    r = await c.get("/api/v1/reports/funding-cashflow", headers=h2)
    assert r.status_code == 403
