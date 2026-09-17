"""Direct-enrolment vs recruitment-funnel signal for the journey tracker.

person_has_application drives whether the student page shows the "Applicant" stage on the
journey circle. It has to reject *synthetic* Applications — the ones the HESA data-fixup
script writes purely so ENTRYROUTE can be populated — otherwise every directly-enrolled
student (ICR G2) gets stamped as a funnel entrant on the journey and the tab wiring lies.

A real recruitment journey always leaves a trail of CandidateStageHistory rows; a synthetic
fixup Application has none. That's the discriminator this test pins down.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.person.models import Person
from app.modules.recruitment.constants import ApplicationRoute, CandidateStage
from app.modules.recruitment.models import Application, CandidateStageHistory
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.service import StudentService


def _svc(session) -> StudentService:
    return StudentService(StudentRepository(session))


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        yield s
    await eng.dispose()


async def _make_person(s) -> Person:
    p = Person(given_name="Ada", family_name="Lovelace", email=f"ada-{uuid.uuid4().hex[:6]}@example.com")
    s.add(p)
    await s.flush()
    return p


@pytest.mark.asyncio
async def test_returns_false_when_no_application(session):
    p = await _make_person(session)
    await session.commit()
    assert await _svc(session).person_has_application(p.id) is False


@pytest.mark.asyncio
async def test_returns_false_for_synthetic_fixup_application(session):
    """A fixup-created Application has no CandidateStageHistory — it must NOT flip the
    person into 'came via application'. Otherwise the journey tracker shows Applicant on a
    student who never went through recruitment."""
    p = await _make_person(session)
    session.add(Application(
        person_id=p.id, route=ApplicationRoute.opportunity_led,
        current_stage=CandidateStage.converted,
        submitted_at=datetime.now(timezone.utc),
        proposal_document_ref="__fixup_hesa_demo:entryroute_only__",
    ))
    await session.commit()

    assert await _svc(session).person_has_application(p.id) is False


@pytest.mark.asyncio
async def test_returns_true_for_real_application_with_history(session):
    """A real applicant went through at least one funnel transition (e.g. applicant → shortlisted).
    That leaves a CandidateStageHistory row — the honest signal that recruitment actually
    happened."""
    p = await _make_person(session)
    app = Application(
        person_id=p.id, route=ApplicationRoute.student_led,
        current_stage=CandidateStage.shortlisted,
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(app)
    await session.flush()
    session.add(CandidateStageHistory(
        application_id=app.id,
        from_stage=CandidateStage.applicant,
        to_stage=CandidateStage.shortlisted,
        moved_at=datetime.now(timezone.utc),
    ))
    await session.commit()

    assert await _svc(session).person_has_application(p.id) is True
