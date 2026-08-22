"""Funding lineage and integrity (Phase 6.3 — CIO vision GAP-03).

Answers the single trace the CIO asked for:

    Student → Research Project → Research Award → Funder → Funding Arrangement → Stipend

and then checks that the chain makes sense. Every finding carries the dates or amounts that
produced it, so it can be defended rather than merely displayed.

**No new dependencies.** The gap analysis suggested pandas + intervaltree; for the handful of
arrangements a student holds, a sorted list and plain date arithmetic is clearer, faster and
easier to audit than an interval library.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.funding.constants import COMMITTED_PAYMENT_STATES, FundingStatus, PaymentStatus
from app.modules.funding.models import FundingArrangement, FundingSource, StipendPayment
from app.modules.person.models import Person
from app.modules.research.models import ResearchAward
from app.modules.student_record.models import ResearchProject, Student

# Severities. `error` = the record is wrong or the student will be harmed; `warning` = worth a look.
ERROR = "error"
WARNING = "warning"
INFO = "info"



def _finding(code: str, severity: str, message: str, **detail) -> dict:
    return {"code": code, "severity": severity, "message": message, "detail": detail}


class FundingLineageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _student(self, student_id: uuid.UUID) -> tuple[Student, Person]:
        row = (await self.session.execute(
            select(Student, Person).join(Person, Person.id == Student.person_id)
            .where(Student.id == student_id)
        )).first()
        if row is None:
            raise NotFoundError("Student not found")
        return row[0], row[1]

    async def lineage(self, student_id: uuid.UUID) -> dict:
        """The full chain for one student, with integrity findings attached."""
        student, person = await self._student(student_id)

        project = (await self.session.execute(
            select(ResearchProject).where(ResearchProject.student_id == student_id)
        )).scalars().first()

        arrangements = list((await self.session.execute(
            select(FundingArrangement)
            .where(FundingArrangement.student_id == student_id)
            .order_by(FundingArrangement.valid_from)
        )).scalars().all())

        # Awards reachable from either the project or any arrangement.
        award_ids = {a.research_award_id for a in arrangements if a.research_award_id}
        if project and project.research_award_id:
            award_ids.add(project.research_award_id)
        awards = {}
        if award_ids:
            rows = (await self.session.execute(
                select(ResearchAward).where(ResearchAward.id.in_(list(award_ids)))
            )).scalars().all()
            awards = {a.id: a for a in rows}

        funder_ids = {a.funder_id for a in awards.values() if a.funder_id}
        funder_ids |= {a.funding_source_id for a in arrangements if a.funding_source_id}
        funders = {}
        if funder_ids:
            rows = (await self.session.execute(
                select(FundingSource).where(FundingSource.id.in_(list(funder_ids)))
            )).scalars().all()
            funders = {f.id: f for f in rows}

        payments = list((await self.session.execute(
            select(StipendPayment).where(StipendPayment.student_id == student_id)
        )).scalars().all())
        by_arrangement: dict[uuid.UUID, list[StipendPayment]] = {}
        for p in payments:
            by_arrangement.setdefault(p.arrangement_id, []).append(p)

        def award_out(aw: ResearchAward | None) -> dict | None:
            if aw is None:
                return None
            f = funders.get(aw.funder_id) if aw.funder_id else None
            return {
                "id": str(aw.id), "awardRef": aw.award_ref, "title": aw.title,
                "value": str(aw.value) if aw.value is not None else None,
                "currency": aw.currency,
                "startDate": aw.start_date.isoformat() if aw.start_date else None,
                "endDate": aw.end_date.isoformat() if aw.end_date else None,
                "funder": {"id": str(f.id), "name": f.name} if f else None,
                "sourceSystem": aw.source_system,
            }

        arrangement_rows = []
        for a in arrangements:
            paid = sum((p.amount for p in by_arrangement.get(a.id, []) if p.status is PaymentStatus.paid), Decimal("0"))
            committed = sum((p.amount for p in by_arrangement.get(a.id, []) if p.status in COMMITTED_PAYMENT_STATES), Decimal("0"))
            src = funders.get(a.funding_source_id) if a.funding_source_id else None
            arrangement_rows.append({
                "id": str(a.id),
                "fundingType": a.funding_type.value if hasattr(a.funding_type, "value") else a.funding_type,
                "status": a.status.value if hasattr(a.status, "value") else a.status,
                "validFrom": a.valid_from.isoformat(),
                "validTo": a.valid_to.isoformat() if a.valid_to else None,
                "stipendAmount": str(a.stipend_amount) if a.stipend_amount is not None else None,
                "currency": a.currency,
                "contributionPct": a.contribution_pct,
                "costCentre": a.cost_centre, "projectCode": a.project_code,
                "funderReference": a.funder_reference,
                "fundingSource": {"id": str(src.id), "name": src.name} if src else None,
                "award": award_out(awards.get(a.research_award_id)) if a.research_award_id else None,
                "instalments": len(by_arrangement.get(a.id, [])),
                "paidTotal": str(paid), "committedTotal": str(committed),
            })

        project_award = awards.get(project.research_award_id) if project and project.research_award_id else None
        from app.modules.settings.service import setting_value

        min_gap = await setting_value(self.session, "funding.min_gap_days")
        findings = self._check(student, project, arrangements, awards, payments, min_gap=min_gap)

        return {
            "student": {
                "id": str(student.id), "studentRef": student.student_ref,
                "personName": f"{person.given_name} {person.family_name}",
                "status": student.status.value if hasattr(student.status, "value") else student.status,
                "startDate": student.start_date.isoformat() if student.start_date else None,
                "expectedEndDate": student.expected_end_date.isoformat() if student.expected_end_date else None,
                "link": f"/students/{student.id}",
            },
            "project": {
                "id": str(project.id), "researchTopic": project.research_topic,
                "researchGroup": project.research_group,
                "startDate": project.start_date.isoformat() if project.start_date else None,
                "endDate": project.end_date.isoformat() if project.end_date else None,
                "award": award_out(project_award),
            } if project else None,
            "arrangements": arrangement_rows,
            "totals": {
                "paid": str(sum((p.amount for p in payments if p.status is PaymentStatus.paid), Decimal("0"))),
                "committed": str(sum((p.amount for p in payments if p.status in COMMITTED_PAYMENT_STATES), Decimal("0"))),
                "currency": payments[0].currency if payments else None,
            },
            "findings": findings,
            "complete": not any(f["severity"] == ERROR for f in findings),
        }

    # ------------------------------------------------------------------
    # Integrity checks
    # ------------------------------------------------------------------

    def _check(
        self,
        student: Student,
        project: ResearchProject | None,
        arrangements: list[FundingArrangement],
        awards: dict[uuid.UUID, ResearchAward],
        payments: list[StipendPayment],
        min_gap: int = 7,
    ) -> list[dict]:
        findings: list[dict] = []
        funded = [a for a in arrangements if a.status is not FundingStatus.planned]

        # --- lineage completeness ---
        if project is None:
            findings.append(_finding(
                "no_project", WARNING,
                "This student has no research project record, so their work cannot be traced to an award.",
            ))
        elif project.research_award_id is None:
            findings.append(_finding(
                "project_not_linked_to_award", INFO,
                "The research project is not linked to a research award "
                "(expected for self-funded or studentship-funded students).",
            ))

        for a in arrangements:
            if a.research_award_id is None and (a.project_code or a.funder_reference):
                findings.append(_finding(
                    "arrangement_award_unlinked", WARNING,
                    "A funding arrangement carries finance references but is not linked to a research award, "
                    "so spend cannot be attributed.",
                    arrangementId=str(a.id), projectCode=a.project_code,
                    funderReference=a.funder_reference,
                ))

        # --- coverage: gaps, overlaps, early expiry ---
        current = sorted(
            [a for a in funded if a.status is not FundingStatus.ended or a.valid_to],
            key=lambda a: a.valid_from,
        )
        if student.start_date and current:
            first = current[0]
            if first.valid_from > student.start_date + timedelta(days=min_gap):
                findings.append(_finding(
                    "unfunded_at_start", WARNING,
                    f"Funding starts {(first.valid_from - student.start_date).days} days after the "
                    f"student began.",
                    studentStart=student.start_date.isoformat(),
                    firstFundingFrom=first.valid_from.isoformat(),
                ))

        for prev, nxt in zip(current, current[1:]):
            prev_end = prev.valid_to
            if prev_end is None:
                continue  # open-ended; the overlap check below covers it
            gap = (nxt.valid_from - prev_end).days
            if gap > min_gap:
                findings.append(_finding(
                    "funding_gap", ERROR,
                    f"{gap} days with no funding between {prev_end.isoformat()} and "
                    f"{nxt.valid_from.isoformat()}.",
                    from_=prev_end.isoformat(), to=nxt.valid_from.isoformat(), days=gap,
                ))
            elif gap < 0:
                # Overlap. Legitimate for blended funding, but only if the shares add up.
                total_pct = (prev.contribution_pct or 100) + (nxt.contribution_pct or 100)
                if total_pct > 100:
                    findings.append(_finding(
                        "funding_overlap", WARNING,
                        f"Two arrangements overlap by {abs(gap)} days and their contributions total "
                        f"{total_pct}%, which exceeds 100%.",
                        days=abs(gap), totalContributionPct=total_pct,
                    ))

        open_ended = [a for a in current if a.valid_to is None]
        last_end = max((a.valid_to for a in current if a.valid_to), default=None)
        if student.expected_end_date and not open_ended and last_end:
            if last_end < student.expected_end_date:
                short = (student.expected_end_date - last_end).days
                findings.append(_finding(
                    "funding_ends_before_expected_end", ERROR,
                    f"Funding ends {short} days before the expected end of study "
                    f"({last_end.isoformat()} vs {student.expected_end_date.isoformat()}).",
                    fundingEnds=last_end.isoformat(),
                    expectedEnd=student.expected_end_date.isoformat(), shortfallDays=short,
                ))

        # --- award consistency ---
        for a in arrangements:
            award = awards.get(a.research_award_id) if a.research_award_id else None
            if award is None:
                continue
            if award.end_date and a.valid_to and a.valid_to > award.end_date:
                findings.append(_finding(
                    "funding_outlives_award", ERROR,
                    f"Funding runs to {a.valid_to.isoformat()} but award {award.award_ref} ends "
                    f"{award.end_date.isoformat()}.",
                    arrangementId=str(a.id), awardRef=award.award_ref,
                ))
            if award.start_date and a.valid_from < award.start_date:
                findings.append(_finding(
                    "funding_precedes_award", WARNING,
                    f"Funding starts {a.valid_from.isoformat()}, before award {award.award_ref} "
                    f"begins {award.start_date.isoformat()}.",
                    arrangementId=str(a.id), awardRef=award.award_ref,
                ))

        # Committed stipend against each award's headline value (this student only — a fuller
        # picture needs the cohort view, which `cohort_integrity` provides).
        for award_id, award in awards.items():
            if award.value is None:
                continue
            arr_ids = {a.id for a in arrangements if a.research_award_id == award_id}
            committed = sum(
                (p.amount for p in payments
                 if p.arrangement_id in arr_ids and p.status in COMMITTED_PAYMENT_STATES),
                Decimal("0"),
            )
            if committed > award.value:
                findings.append(_finding(
                    "stipend_exceeds_award_value", ERROR,
                    f"Committed stipend ({committed}) exceeds the value of award "
                    f"{award.award_ref} ({award.value}).",
                    awardRef=award.award_ref, committed=str(committed), awardValue=str(award.value),
                ))
        return findings

    # ------------------------------------------------------------------
    # Cohort view — the question with no screen
    # ------------------------------------------------------------------

    async def cohort_integrity(
        self, *, allowed_ids: list[uuid.UUID] | None = None, severity: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Every student whose funding chain has a problem, with the reasons.

        **Bulk-loaded deliberately.** Calling `lineage()` per student is ~6 queries each, which is
        O(students × queries): measured at 1.2–1.9 s for 266 students and would breach the 2 s
        report target at institutional scale. Here every table is read **once** and `_check` (which
        is pure) runs in memory, so cost is a handful of queries regardless of cohort size.
        """
        from app.modules.student_record.constants import StudentStatus

        stmt = (
            select(Student, Person).join(Person, Person.id == Student.person_id)
            .where(Student.status.in_([StudentStatus.registered, StudentStatus.active]))
        )
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))
        rows = (await self.session.execute(stmt)).all()
        student_ids = [st.id for st, _ in rows]
        if not student_ids:
            return {"checked": 0, "withFindings": 0, "errors": 0, "warnings": 0, "students": []}

        # --- one read per table, then group in memory ---
        projects: dict[uuid.UUID, ResearchProject] = {
            p.student_id: p for p in (await self.session.execute(
                select(ResearchProject).where(ResearchProject.student_id.in_(student_ids))
            )).scalars().unique().all()
        }
        arrangements: dict[uuid.UUID, list[FundingArrangement]] = {}
        for a in (await self.session.execute(
            select(FundingArrangement)
            .where(FundingArrangement.student_id.in_(student_ids))
            .order_by(FundingArrangement.valid_from)
        )).scalars().all():
            arrangements.setdefault(a.student_id, []).append(a)

        payments: dict[uuid.UUID, list[StipendPayment]] = {}
        for p in (await self.session.execute(
            select(StipendPayment).where(StipendPayment.student_id.in_(student_ids))
        )).scalars().all():
            payments.setdefault(p.student_id, []).append(p)

        award_ids = {a.research_award_id for lst in arrangements.values() for a in lst if a.research_award_id}
        award_ids |= {p.research_award_id for p in projects.values() if p.research_award_id}
        awards: dict[uuid.UUID, ResearchAward] = {}
        if award_ids:
            awards = {a.id: a for a in (await self.session.execute(
                select(ResearchAward).where(ResearchAward.id.in_(list(award_ids)))
            )).scalars().all()}

        from app.modules.settings.service import setting_value

        min_gap = await setting_value(self.session, "funding.min_gap_days")
        students, counts = [], {ERROR: 0, WARNING: 0, INFO: 0}
        for student, person in rows:
            findings = [
                f for f in self._check(
                    student, projects.get(student.id), arrangements.get(student.id, []),
                    awards, payments.get(student.id, []), min_gap=min_gap,
                )
                if f["severity"] != INFO
            ]
            if severity:
                findings = [f for f in findings if f["severity"] == severity]
            if not findings:
                continue
            for f in findings:
                counts[f["severity"]] = counts.get(f["severity"], 0) + 1
            students.append({
                "id": str(student.id), "studentRef": student.student_ref,
                "personName": f"{person.given_name} {person.family_name}",
                "status": student.status.value if hasattr(student.status, "value") else student.status,
                "startDate": student.start_date.isoformat() if student.start_date else None,
                "expectedEndDate": student.expected_end_date.isoformat() if student.expected_end_date else None,
                "link": f"/students/{student.id}",
                "findings": findings,
                "worstSeverity": ERROR if any(f["severity"] == ERROR for f in findings) else WARNING,
            })

        students.sort(key=lambda s: (s["worstSeverity"] != ERROR, s["personName"]))
        return {"checked": len(student_ids), "withFindings": len(students),
                "errors": counts[ERROR], "warnings": counts[WARNING],
                "students": students[:limit]}
