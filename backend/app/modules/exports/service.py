"""Export service (arch §13.4). Runs the job and stores the CSV (object-store stand-in)."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.modules.exports.constants import EXPORT_KINDS, ExportStatus
from app.modules.exports.models import ExportJob
from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.person.models import Person
from app.modules.student_record.models import Programme, Student


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_and_run(self, kind: str) -> ExportJob:
        if kind not in EXPORT_KINDS:
            raise ValidationAppError(f"Unknown export kind: {kind}")
        job = ExportJob(kind=kind, status=ExportStatus.running, created_at=_now())
        self.session.add(job)
        await self.session.flush()
        try:
            if kind == "pgr_enterprise_360":
                filename, rows, content = await self._run_enterprise_360()
            else:
                filename, rows, content = await self._run_students_statutory()
            job.filename, job.row_count, job.content = filename, rows, content
            job.status = ExportStatus.complete
            job.completed_at = _now()
        except Exception as exc:  # pragma: no cover - defensive
            job.status = ExportStatus.failed
            job.error = str(exc)[:500]
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def _run_students_statutory(self) -> tuple[str, int, str]:
        # One population, statutory fields (arch §13.2 statutory lens).
        programmes = {p.id: p.name for p in (await self.session.execute(select(Programme))).scalars().all()}
        active_funding: dict[uuid.UUID, str] = {}
        for fa in (await self.session.execute(
            select(FundingArrangement).where(
                FundingArrangement.status == FundingStatus.active, FundingArrangement.valid_to.is_(None)
            )
        )).scalars().all():
            active_funding.setdefault(fa.student_id, fa.funding_type.value)

        rows = (await self.session.execute(
            select(Student, Person).join(Person, Person.id == Student.person_id).order_by(Student.student_ref)
        )).all()

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["student_ref", "given_name", "family_name", "nationality", "programme",
                    "status", "study_mode", "start_date", "expected_end_date", "funding_type"])
        for student, person in rows:
            w.writerow([
                student.student_ref, person.given_name, person.family_name, person.nationality or "",
                programmes.get(student.programme_id, ""), student.status.value, student.study_mode.value,
                student.start_date.isoformat() if student.start_date else "",
                student.expected_end_date.isoformat() if student.expected_end_date else "",
                active_funding.get(student.id, ""),
            ])
        stamp = _now().strftime("%Y%m%d")
        return f"students_statutory_{stamp}.csv", len(rows), buf.getvalue()

    async def _run_enterprise_360(self) -> tuple[str, int, str]:
        from app.modules.reporting.analytics import AnalyticsService

        data = await AnalyticsService(self.session).enterprise_360()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["student_ref", "name", "status", "research_area", "research_topic",
                    "funding_type", "funding_source", "is_employee", "programme", "nationality"])
        for r in data["population"]:
            w.writerow([
                r["studentRef"], r["personName"], r["student"]["status"],
                r["research"]["area"] or "", r["research"]["topic"] or "",
                (r["funding"] or {}).get("type", ""), (r["funding"] or {}).get("source", ""),
                "yes" if r["workforce"]["isEmployee"] else "no",
                r["statutory"]["programme"] or "", r["statutory"]["nationality"] or "",
            ])
        stamp = _now().strftime("%Y%m%d")
        return f"pgr_enterprise_360_{stamp}.csv", len(data["population"]), buf.getvalue()

    async def get(self, job_id: uuid.UUID) -> ExportJob:
        job = (await self.session.execute(select(ExportJob).where(ExportJob.id == job_id))).scalar_one_or_none()
        if job is None:
            raise NotFoundError("Export job not found")
        return job

    async def list_recent(self, limit: int = 20) -> list[ExportJob]:
        stmt = select(ExportJob).order_by(ExportJob.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
