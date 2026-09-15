"""Taught-lifecycle business rules (ICR G1).

Classification is credit-weighted: each module's mark is the weight_pct-weighted mean of its
marked assessments (normalised to a percentage of each assessment's max_mark); the programme mark
is the credit-weighted mean of module marks, with the dissertation folded in as a component whose
credit weight is the programme's remaining credits. The mark -> band thresholds below are the
canonical UK taught-postgraduate defaults; making them Settings-configurable per institution is a
fast-follow, not part of the week-1 MVP (they are deliberately in one place so that change is a
small one).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.student_record.constants import ProgrammeType
from app.modules.student_record.models import Programme, Student
from app.modules.student_record.repository import StudentRepository
from app.modules.taught.constants import ClassificationBand, ModuleEnrolmentStatus
from app.modules.taught.models import (
    AssessmentResult,
    Dissertation,
    ModuleAssessment,
    ModuleEnrolment,
    TaughtAward,
    TaughtModule,
)
from app.modules.taught.repository import TaughtRepository
from app.modules.taught.schemas import (
    AssessmentCreate,
    DissertationUpsert,
    ModuleCreate,
    ModuleUpdate,
    ResultRecord,
)

# Policy defaults (see module docstring). Ordered high -> low; first threshold met wins.
CLASSIFICATION_THRESHOLDS: list[tuple[Decimal, ClassificationBand]] = [
    (Decimal("70"), ClassificationBand.distinction),
    (Decimal("60"), ClassificationBand.merit),
    (Decimal("50"), ClassificationBand.pass_),
]
PASS_MARK = Decimal("50")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _band_for(mark: Decimal) -> ClassificationBand:
    for threshold, band in CLASSIFICATION_THRESHOLDS:
        if mark >= threshold:
            return band
    return ClassificationBand.fail


class TaughtService:
    def __init__(self, repo: TaughtRepository) -> None:
        self.repo = repo
        self.session = repo.session

    # --- students / programmes ---
    async def _student(self, student_id: uuid.UUID, *, allowed_ids=None) -> Student:
        s = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if s is None:
            raise NotFoundError("Student not found")
        return s

    async def _programme(self, programme_id: uuid.UUID | None) -> Programme | None:
        if programme_id is None:
            return None
        return await self.session.get(Programme, programme_id)

    # --- modules / assessments (programme configuration) ---
    def _assessment_out(self, a: ModuleAssessment) -> dict:
        return {
            "id": a.id, "module_id": a.module_id, "title": a.title,
            "assessment_type": a.assessment_type, "weight_pct": a.weight_pct,
            "max_mark": a.max_mark, "due_date": a.due_date,
        }

    def _module_out(self, m: TaughtModule) -> dict:
        return {
            "id": m.id, "programme_id": m.programme_id, "code": m.code, "title": m.title,
            "credits": m.credits, "term": m.term,
            "assessments": [self._assessment_out(a) for a in m.assessments],
        }

    async def list_modules(self, programme_id: uuid.UUID) -> list[dict]:
        return [self._module_out(m) for m in await self.repo.modules_for_programme(programme_id)]

    async def create_module(self, programme_id: uuid.UUID, data: ModuleCreate) -> dict:
        programme = await self._programme(programme_id)
        if programme is None:
            raise NotFoundError("Programme not found")
        m = TaughtModule(
            programme_id=programme_id, code=data.code, title=data.title,
            credits=data.credits, term=data.term,
        )
        self.repo.add(m)
        await self.session.commit()
        m = await self.repo.get_module(m.id)
        return self._module_out(m)

    async def update_module(self, module_id: uuid.UUID, data: ModuleUpdate) -> dict:
        m = await self.repo.get_module(module_id)
        if m is None:
            raise NotFoundError("Module not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(m, field, value)
        await self.session.commit()
        m = await self.repo.get_module(module_id)
        return self._module_out(m)

    async def add_assessment(self, module_id: uuid.UUID, data: AssessmentCreate) -> dict:
        m = await self.repo.get_module(module_id)
        if m is None:
            raise NotFoundError("Module not found")
        a = ModuleAssessment(
            module_id=module_id, title=data.title, assessment_type=data.assessment_type,
            weight_pct=data.weight_pct, max_mark=data.max_mark, due_date=data.due_date,
        )
        self.repo.add(a)
        await self.session.commit()
        await self.session.refresh(a)
        return self._assessment_out(a)

    # --- enrolments / results ---
    async def enrol(self, student_id: uuid.UUID, data, *, allowed_ids=None) -> dict:
        await self._student(student_id, allowed_ids=allowed_ids)
        module = await self.repo.get_module(data.module_id)
        if module is None:
            raise NotFoundError("Module not found")
        if await self.repo.existing_enrolment(student_id, data.module_id, data.academic_year):
            raise ConflictError("Student is already enrolled on this module for that academic year")
        e = ModuleEnrolment(
            student_id=student_id, module_id=data.module_id, academic_year=data.academic_year,
            status=ModuleEnrolmentStatus.enrolled,
        )
        self.repo.add(e)
        await self.session.commit()
        e = await self.repo.get_enrolment(e.id)
        return await self._enrolment_out(e)

    async def set_enrolment_status(
        self, enrolment_id: uuid.UUID, status: ModuleEnrolmentStatus
    ) -> dict:
        e = await self.repo.get_enrolment(enrolment_id)
        if e is None:
            raise NotFoundError("Enrolment not found")
        e.status = status
        await self.session.commit()
        e = await self.repo.get_enrolment(enrolment_id)
        return await self._enrolment_out(e)

    async def record_result(
        self, enrolment_id: uuid.UUID, data: ResultRecord, *, user_id=None
    ) -> dict:
        e = await self.repo.get_enrolment(enrolment_id)
        if e is None:
            raise NotFoundError("Enrolment not found")
        assessment = await self.repo.get_assessment(data.assessment_id)
        if assessment is None:
            raise NotFoundError("Assessment not found")
        if assessment.module_id != e.module_id:
            raise WorkflowError("That assessment does not belong to this enrolment's module")
        marked = data.mark is not None
        r = AssessmentResult(
            module_enrolment_id=enrolment_id, assessment_id=data.assessment_id,
            mark=data.mark, grade=data.grade, is_resit=data.is_resit,
            submitted_at=data.submitted_at,
            marked_at=datetime.now(timezone.utc) if marked else None,
            marked_by_user_id=user_id if marked else None,
        )
        self.repo.add(r)
        await self.session.commit()
        e = await self.repo.get_enrolment(enrolment_id)
        return await self._enrolment_out(e)

    async def list_enrolments(self, student_id: uuid.UUID, *, allowed_ids=None) -> list[dict]:
        await self._student(student_id, allowed_ids=allowed_ids)
        rows = await self.repo.enrolments_for_student(student_id)
        return [await self._enrolment_out(e) for e in rows]

    # --- classification helpers ---
    def _effective_results(self, enrolment: ModuleEnrolment) -> dict[uuid.UUID, AssessmentResult]:
        """Best marked attempt per assessment (a resit never lowers the recorded mark)."""
        best: dict[uuid.UUID, AssessmentResult] = {}
        for r in enrolment.results:
            if r.mark is None:
                continue
            cur = best.get(r.assessment_id)
            if cur is None or r.mark > cur.mark:
                best[r.assessment_id] = r
        return best

    def _module_mark(self, module: TaughtModule, enrolment: ModuleEnrolment) -> Decimal | None:
        eff = self._effective_results(enrolment)
        if not eff:
            return None
        total_w = Decimal("0")
        acc = Decimal("0")
        for a in module.assessments:
            r = eff.get(a.id)
            if r is None:
                continue
            pct = (r.mark / a.max_mark * 100) if a.max_mark else r.mark
            acc += pct * a.weight_pct
            total_w += a.weight_pct
        if total_w == 0:
            return None
        return _q(acc / total_w)

    async def _enrolment_out(self, e: ModuleEnrolment) -> dict:
        module = await self.repo.get_module(e.module_id)
        mark = self._module_mark(module, e) if module else None
        return {
            "id": e.id, "student_id": e.student_id, "module_id": e.module_id,
            "module_code": module.code if module else None,
            "module_title": module.title if module else None,
            "credits": module.credits if module else None,
            "academic_year": e.academic_year, "status": e.status,
            "module_mark": mark,
            "results": [
                {
                    "id": r.id, "assessment_id": r.assessment_id, "mark": r.mark,
                    "grade": r.grade, "is_resit": r.is_resit,
                    "submitted_at": r.submitted_at, "marked_at": r.marked_at,
                }
                for r in e.results
            ],
        }

    # --- dissertation ---
    async def _dissertation_out(self, d: Dissertation | None) -> dict | None:
        if d is None:
            return None
        name = None
        if d.supervisor_person_id:
            from app.modules.person.models import Person
            person = await self.session.get(Person, d.supervisor_person_id)
            if person:
                name = f"{person.given_name} {person.family_name}"
        return {
            "id": d.id, "student_id": d.student_id, "title": d.title,
            "supervisor_person_id": d.supervisor_person_id, "supervisor_name": name,
            "submitted_at": d.submitted_at, "marked_at": d.marked_at,
            "mark": d.mark, "grade": d.grade,
        }

    async def upsert_dissertation(
        self, student_id: uuid.UUID, data: DissertationUpsert, *, allowed_ids=None
    ) -> dict:
        await self._student(student_id, allowed_ids=allowed_ids)
        d = await self.repo.get_dissertation(student_id)
        fields = data.model_dump(exclude_unset=True)
        newly_marked = "mark" in fields and fields["mark"] is not None
        if d is None:
            d = Dissertation(student_id=student_id, **fields)
            if newly_marked:
                d.marked_at = datetime.now(timezone.utc)
            self.repo.add(d)
        else:
            for field, value in fields.items():
                setattr(d, field, value)
            if newly_marked:
                d.marked_at = datetime.now(timezone.utc)
        await self.session.commit()
        d = await self.repo.get_dissertation(student_id)
        return await self._dissertation_out(d)

    # --- award / classification ---
    async def compute_award(self, student_id: uuid.UUID, *, user_id=None, allowed_ids=None) -> dict:
        student = await self._student(student_id, allowed_ids=allowed_ids)
        programme = await self._programme(student.programme_id)
        if programme is None or programme.programme_type != ProgrammeType.taught:
            raise WorkflowError("Classification only applies to a taught programme")

        enrolments = await self.repo.enrolments_for_student(student_id)
        components: list[tuple[Decimal, Decimal]] = []  # (mark, credit weight)
        module_credit_sum = 0
        credits_achieved = 0
        for e in enrolments:
            module = await self.repo.get_module(e.module_id)
            if module is None:
                continue
            mark = self._module_mark(module, e)
            if mark is None:
                continue
            weight = Decimal(module.credits) if module.credits else Decimal("1")
            components.append((mark, weight))
            module_credit_sum += module.credits or 0
            if mark >= PASS_MARK:
                credits_achieved += module.credits or 0

        dissertation = await self.repo.get_dissertation(student_id)
        if dissertation is not None and dissertation.mark is not None:
            target = programme.taught_total_credits
            if target and target > module_credit_sum:
                diss_credits = Decimal(target - module_credit_sum)
            elif components:
                # No explicit remaining credits — weight the dissertation like an average module.
                diss_credits = sum((w for _, w in components), Decimal("0")) / Decimal(len(components))
            else:
                diss_credits = Decimal("1")
            components.append((dissertation.mark, diss_credits))

        if not components:
            raise WorkflowError("No marked modules or dissertation yet — nothing to classify")

        total_w = sum((w for _, w in components), Decimal("0"))
        final = _q(sum((m * w for m, w in components), Decimal("0")) / total_w)
        band = _band_for(final)

        award = await self.repo.get_award(student_id)
        if award is None:
            award = TaughtAward(student_id=student_id)
            self.repo.add(award)
        award.final_mark = final
        award.classification = band
        award.credits_achieved = credits_achieved
        award.decided_by_user_id = user_id
        award.decided_at = datetime.now(timezone.utc)
        await self.session.commit()
        award = await self.repo.get_award(student_id)
        return self._award_out(award)

    def _award_out(self, a: TaughtAward | None) -> dict | None:
        if a is None:
            return None
        return {
            "student_id": a.student_id, "final_mark": a.final_mark,
            "classification": a.classification, "credits_achieved": a.credits_achieved,
            "decided_at": a.decided_at,
        }

    # --- aggregate for the student-360 taught panel ---
    async def taught_record(self, student_id: uuid.UUID, *, allowed_ids=None) -> dict:
        student = await self._student(student_id, allowed_ids=allowed_ids)
        programme = await self._programme(student.programme_id)
        enrolments = await self.repo.enrolments_for_student(student_id)
        enr_out = [await self._enrolment_out(e) for e in enrolments]
        credits_enrolled = sum((e.get("credits") or 0) for e in enr_out)
        dissertation = await self.repo.get_dissertation(student_id)
        award = await self.repo.get_award(student_id)
        return {
            "student_id": student_id,
            "programme_type": (programme.programme_type.value if programme else "research"),
            "total_credits_target": programme.taught_total_credits if programme else None,
            "credits_enrolled": credits_enrolled,
            "enrolments": enr_out,
            "dissertation": await self._dissertation_out(dissertation),
            "award": self._award_out(award),
        }
