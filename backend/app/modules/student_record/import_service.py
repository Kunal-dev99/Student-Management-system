"""Cohort import — ICR G2 (slice B).

Bulk-enrol a batch of already-accepted students from a CSV the institution exports from its own
recruitment system. Two phases so nothing is written blind:

    preview(file)  -> per-row validation, duplicate detection, resolved programme. No writes.
    commit(file)   -> creates a student per OK row via the SAME enrol service path a single
                      enrolment uses. Idempotent on the student reference: a row whose ref already
                      exists is skipped, so re-running the same file is safe.

CSV only for now (openpyxl/pandas are not dependencies); headers are matched case-insensitively
against a set of common aliases, so an export does not have to use our exact column names.
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.modules.funding.constants import FundingType
from app.modules.funding.models import FundingSource
from app.modules.funding.schemas import ArrangementCreate
from app.modules.person.models import Person
from app.modules.person.schemas import PersonCreate
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.service import StudentService

# canonical field -> accepted header spellings (all compared lower-cased, stripped)
_ALIASES: dict[str, set[str]] = {
    "student_ref": {"ref", "student_ref", "student ref", "studentref", "reference"},
    "given_name": {"given_name", "given name", "first_name", "first name", "firstname", "forename"},
    "family_name": {"family_name", "family name", "last_name", "last name", "lastname", "surname"},
    "name": {"name", "full name", "fullname", "student name", "student"},
    "email": {"email", "e-mail", "email address"},
    "programme_code": {"programme", "programme_code", "programme code", "course", "course code",
                       "course_code", "prog", "programme/course"},
    "start_date": {"start", "start_date", "start date", "commencement", "start date"},
    "study_mode": {"mode", "study_mode", "study mode", "attendance"},
    "status": {"status"},
    "funder": {"funder", "funding", "funding source", "funding_source", "sponsor"},
}

_MODE = {
    "full_time": StudyMode.full_time, "full time": StudyMode.full_time, "ft": StudyMode.full_time,
    "full": StudyMode.full_time, "fulltime": StudyMode.full_time,
    "part_time": StudyMode.part_time, "part time": StudyMode.part_time, "pt": StudyMode.part_time,
    "part": StudyMode.part_time, "parttime": StudyMode.part_time,
}
_STATUS = {"registered": StudentStatus.registered, "prospective": StudentStatus.prospective}


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{raw}' (use YYYY-MM-DD or DD/MM/YYYY)")


@dataclass
class RowResult:
    line: int
    given_name: str = ""
    family_name: str = ""
    email: str | None = None
    student_ref: str | None = None
    programme_code: str | None = None
    programme_name: str | None = None
    study_mode: StudyMode = StudyMode.full_time
    status: StudentStatus = StudentStatus.registered
    funder: str | None = None
    action: str = "create"          # create | attach | skip | error
    messages: list[str] = field(default_factory=list)
    # resolved internals used by commit (not serialised raw over the wire)
    _programme_id: uuid.UUID | None = None
    _person_id: uuid.UUID | None = None
    _funding_source_id: uuid.UUID | None = None
    _start_date: date | None = None

    def to_out(self) -> dict:
        return {
            "line": self.line,
            "name": f"{self.given_name} {self.family_name}".strip(),
            "email": self.email,
            "studentRef": self.student_ref,
            "programmeCode": self.programme_code,
            "programmeName": self.programme_name,
            "studyMode": self.study_mode.value,
            "status": self.status.value,
            "funder": self.funder,
            "action": self.action,
            "messages": self.messages,
        }


class CohortImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StudentRepository(session)

    # --- parsing ---
    def _normalise_headers(self, fieldnames: list[str]) -> dict[str, str]:
        """Map each canonical field to the actual column header present in the file."""
        present: dict[str, str] = {}
        for col in fieldnames or []:
            key = (col or "").strip().lower()
            for canonical, spellings in _ALIASES.items():
                if key in spellings:
                    present[canonical] = col
                    break
        return present

    def _rows(self, data: bytes) -> tuple[list[dict], dict[str, str]]:
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        header_map = self._normalise_headers(reader.fieldnames or [])
        if "programme_code" not in header_map:
            raise ValidationAppError(
                "The file needs a programme column (e.g. 'programme code'). "
                f"Columns found: {', '.join(reader.fieldnames or []) or '(none)'}"
            )
        if "family_name" not in header_map and "name" not in header_map:
            raise ValidationAppError("The file needs a name column (either 'name' or 'family name').")
        return list(reader), header_map

    # --- validation (shared by preview and commit) ---
    async def _validate(self, data: bytes) -> list[RowResult]:
        rows, hmap = self._rows(data)
        programmes = await self.repo.list_programmes()
        by_code = {p.code.strip().lower(): p for p in programmes if p.code}
        by_name = {p.name.strip().lower(): p for p in programmes}
        sources = (await self.session.execute(select(FundingSource))).scalars().all()
        by_source = {s.name.strip().lower(): s for s in sources}

        seen_refs: set[str] = set()
        results: list[RowResult] = []
        for i, raw in enumerate(rows, start=2):  # line 1 is the header
            def cell(field_key: str) -> str:
                col = hmap.get(field_key)
                return (raw.get(col, "") or "").strip() if col else ""

            r = RowResult(line=i)
            # name
            given, family = cell("given_name"), cell("family_name")
            if not family and cell("name"):
                parts = cell("name").split()
                family = parts[-1] if parts else ""
                given = " ".join(parts[:-1])
            r.given_name, r.family_name = given, family
            r.email = cell("email") or None
            r.student_ref = cell("student_ref") or None
            r.programme_code = cell("programme_code") or None
            r.funder = cell("funder") or None

            # study mode / status
            mode_raw = cell("study_mode").lower()
            if mode_raw and mode_raw not in _MODE:
                r.messages.append(f"unknown mode '{mode_raw}', defaulting to full time")
            r.study_mode = _MODE.get(mode_raw, StudyMode.full_time)
            status_raw = cell("status").lower()
            if status_raw and status_raw not in _STATUS:
                r.messages.append(f"unknown status '{status_raw}', defaulting to registered")
            r.status = _STATUS.get(status_raw, StudentStatus.registered)

            # start date
            try:
                r._start_date = _parse_date(cell("start_date"))
            except ValueError as exc:
                r.action = "error"; r.messages.append(str(exc))

            # required fields
            if not r.family_name:
                r.action = "error"; r.messages.append("missing name")
            prog = None
            if r.programme_code:
                prog = by_code.get(r.programme_code.lower()) or by_name.get(r.programme_code.lower())
            if prog is None:
                r.action = "error"; r.messages.append(f"unknown programme '{r.programme_code or ''}'")
            else:
                r._programme_id = prog.id
                r.programme_name = prog.name

            # funder (non-blocking)
            if r.funder:
                src = by_source.get(r.funder.lower())
                if src is not None:
                    r._funding_source_id = src.id
                else:
                    r.messages.append(f"unknown funder '{r.funder}' — student created without funding")

            # duplicate / attach detection (only if not already an error)
            if r.action != "error":
                if r.student_ref and r.student_ref in seen_refs:
                    r.action = "error"; r.messages.append("duplicate student ref within this file")
                elif r.student_ref and await self.repo.get_by_ref(r.student_ref):
                    r.action = "skip"; r.messages.append("already imported (matching student ref)")
                elif r.email:
                    existing = (await self.session.execute(
                        select(Person).where(func.lower(Person.email) == r.email.lower())
                    )).scalars().first()
                    if existing is not None:
                        if await self.repo.get_by_person(existing.id) is not None:
                            r.action = "error"; r.messages.append("this person is already a student")
                        else:
                            r.action = "attach"; r._person_id = existing.id
                            r.messages.append("attaching to an existing person with this email")
            if r.student_ref:
                seen_refs.add(r.student_ref)
            results.append(r)
        return results

    async def preview(self, data: bytes) -> dict:
        results = await self._validate(data)
        return _summary(results, committed=False)

    async def commit(self, data: bytes) -> dict:
        results = await self._validate(data)
        svc = StudentService(self.repo)
        for r in results:
            if r.action not in ("create", "attach"):
                continue
            try:
                funding = None
                if r._funding_source_id is not None:
                    funding = ArrangementCreate(
                        funding_type=FundingType.external,
                        funding_source_id=r._funding_source_id,
                        valid_from=r._start_date,
                    )
                await svc.enrol(
                    person_id=r._person_id,
                    person_data=None if r._person_id else PersonCreate(
                        given_name=r.given_name or r.family_name,
                        family_name=r.family_name,
                        email=r.email,
                    ),
                    programme_id=r._programme_id,
                    start_date=r._start_date,
                    study_mode=r.study_mode,
                    status=r.status,
                    student_ref=r.student_ref,
                    funding=funding,
                )
                r.messages.append("enrolled")
            except Exception as exc:  # keep going; report the row that failed
                r.action = "error"
                r.messages.append(f"could not enrol: {exc}")
        return _summary(results, committed=True)


def _summary(results: list[RowResult], *, committed: bool) -> dict:
    counts = {"create": 0, "attach": 0, "skip": 0, "error": 0}
    for r in results:
        counts[r.action] = counts.get(r.action, 0) + 1
    return {
        "committed": committed,
        "total": len(results),
        "toCreate": counts["create"] + counts["attach"],
        "skipped": counts["skip"],
        "errors": counts["error"],
        "rows": [r.to_out() for r in results],
    }
