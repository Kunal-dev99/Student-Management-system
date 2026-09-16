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
from app.modules.taught.constants import (
    DEFAULT_GRADING_POLICY,
    ClassificationBand,
    ModuleEnrolmentStatus,
    ModuleOutcome,
)
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

def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _merged_policy(programme: Programme | None) -> dict:
    """The grading policy in force: the programme's overrides on top of the UK-MSc defaults.

    Every threshold (pass mark, resit cap, condonement allowance, classification bands) comes from
    here — nothing is hard-coded to one institution's numbers."""
    policy = dict(DEFAULT_GRADING_POLICY)
    if programme is not None and getattr(programme, "grading_policy", None):
        policy.update({k: v for k, v in programme.grading_policy.items() if v is not None})
    return policy


def _band_for(mark: Decimal, policy: dict) -> ClassificationBand:
    if mark >= Decimal(str(policy["distinctionMark"])):
        return ClassificationBand.distinction
    if mark >= Decimal(str(policy["meritMark"])):
        return ClassificationBand.merit
    if mark >= Decimal(str(policy["passMarkAward"])):
        return ClassificationBand.pass_
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
            "pass_mark": a.pass_mark, "resit_allowed": a.resit_allowed, "resit_cap": a.resit_cap,
        }

    def _module_out(self, m: TaughtModule) -> dict:
        return {
            "id": m.id, "programme_id": m.programme_id, "code": m.code, "title": m.title,
            "credits": m.credits, "term": m.term,
            "level": m.level, "is_core": m.is_core, "convenor_person_id": m.convenor_person_id,
            "assessments": [self._assessment_out(a) for a in m.assessments],
        }

    async def list_modules(self, programme_id: uuid.UUID) -> list[dict]:
        return [self._module_out(m) for m in await self.repo.modules_for_programme(programme_id)]

    async def create_module(self, programme_id: uuid.UUID, data: ModuleCreate) -> dict:
        programme = await self._programme(programme_id)
        if programme is None:
            raise NotFoundError("Programme not found")
        m = TaughtModule(programme_id=programme_id, **data.model_dump())
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
        a = ModuleAssessment(module_id=module_id, **data.model_dump())
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
        if data.is_resit and not assessment.resit_allowed:
            raise WorkflowError("This assessment does not allow a resit")

        # Attempt number = how many results already exist for this component + 1.
        prior = [x for x in e.results if x.assessment_id == data.assessment_id]
        attempt_number = len(prior) + 1

        # Capped resit: a resit mark above the cap is recorded at the cap, and the cap is flagged
        # so it's auditable rather than silently applied.
        mark = data.mark
        capped = False
        if (data.is_resit and marked and assessment.resit_cap is not None
                and mark is not None and mark > assessment.resit_cap):
            mark = assessment.resit_cap
            capped = True

        r = AssessmentResult(
            module_enrolment_id=enrolment_id, assessment_id=data.assessment_id,
            mark=mark, grade=data.grade, is_resit=data.is_resit,
            attempt_number=attempt_number, capped=capped,
            submitted_at=data.submitted_at,
            marked_at=datetime.now(timezone.utc) if marked else None,
            marked_by_user_id=user_id if marked else None,
        )
        # Append to the loaded collection (not just session.add) so _module_mark /
        # _recompute_module_result see the new result in the same transaction.
        e.results.append(r)
        await self.session.flush()
        await self._recompute_module_result(e)
        await self.session.commit()
        e = await self.repo.get_enrolment(enrolment_id)
        return await self._enrolment_out(e)

    async def _recompute_module_result(self, enrolment: ModuleEnrolment) -> None:
        """Refresh the module RESULT (mark, outcome, credits) from the latest assessment marks.

        A module passes when its credit-weighted mark meets the pass mark AND every component is at
        or above its own pass mark; otherwise it fails (a board may later condone it). Credits are
        awarded on a pass (or condonement), never on a plain fail. Runs on every result so the
        stored result never drifts from the marks."""
        module = await self.repo.get_module(enrolment.module_id)
        if module is None:
            return
        programme = await self._programme(module.programme_id)
        policy = _merged_policy(programme)
        mark = self._module_mark(module, enrolment)
        enrolment.final_mark = mark
        if mark is None:
            enrolment.outcome = ModuleOutcome.pending
            enrolment.credits_awarded = None
            return
        eff = self._effective_results(enrolment)
        module_pass = Decimal(str(policy["passMark"]))
        component_ok = all(
            (eff[a.id].mark is None) or (eff[a.id].mark >= a.pass_mark)
            for a in module.assessments if a.id in eff
        )
        if enrolment.condoned:
            enrolment.outcome = ModuleOutcome.condoned
            enrolment.credits_awarded = module.credits or 0
        elif mark >= module_pass and component_ok:
            enrolment.outcome = ModuleOutcome.passed
            enrolment.credits_awarded = module.credits or 0
        else:
            enrolment.outcome = ModuleOutcome.failed
            enrolment.credits_awarded = 0

    async def condone_module(self, enrolment_id: uuid.UUID, *, condoned: bool = True) -> dict:
        """Board action: condone (or un-condone) a failed module — awards its credits despite the
        fail, within the programme's condonement allowance."""
        e = await self.repo.get_enrolment(enrolment_id)
        if e is None:
            raise NotFoundError("Enrolment not found")
        e.condoned = condoned
        await self.session.flush()
        await self._recompute_module_result(e)
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
            "outcome": e.outcome, "credits_awarded": e.credits_awarded, "condoned": e.condoned,
            "results": [
                {
                    "id": r.id, "assessment_id": r.assessment_id, "mark": r.mark,
                    "grade": r.grade, "is_resit": r.is_resit,
                    "attempt_number": r.attempt_number, "capped": r.capped,
                    "submitted_at": r.submitted_at, "marked_at": r.marked_at,
                }
                for r in e.results
            ],
        }

    # --- dissertation ---
    async def _dissertation_out(self, d: Dissertation | None) -> dict | None:
        if d is None:
            return None
        from app.modules.person.models import Person

        async def _name(pid):
            if not pid:
                return None
            p = await self.session.get(Person, pid)
            return f"{p.given_name} {p.family_name}" if p else None

        return {
            "id": d.id, "student_id": d.student_id, "title": d.title,
            "supervisor_person_id": d.supervisor_person_id,
            "supervisor_name": await _name(d.supervisor_person_id),
            "second_marker_person_id": d.second_marker_person_id,
            "second_marker_name": await _name(d.second_marker_person_id),
            "submitted_at": d.submitted_at, "marked_at": d.marked_at,
            "first_mark": d.first_mark, "second_mark": d.second_mark,
            "mark": d.mark, "grade": d.grade, "word_count": d.word_count,
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

        policy = _merged_policy(programme)
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
            # Credits come from the stored module result (a pass or a condoned fail), not a raw
            # mark comparison — so board condonement is honoured.
            credits_achieved += (e.credits_awarded
                                 if e.credits_awarded is not None
                                 else (module.credits or 0 if mark >= Decimal(str(policy["passMark"])) else 0))

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
        band = _band_for(final, policy)

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

    # --- AI board assistant (grounded narration + deterministic recommendations) ---
    async def board_summary(self, student_id: uuid.UUID, *, allowed_ids=None) -> dict:
        """A grounded, one-glance read of a taught student's standing for the board/supervisor:
        counts, the credit position, which modules need a resit/condonement, and the projected
        classification — plus an AI paragraph over exactly those figures (deterministic fallback
        with the model off). Read-only; advises, never decides."""
        student = await self._student(student_id, allowed_ids=allowed_ids)
        programme = await self._programme(student.programme_id)
        if programme is None or programme.programme_type != ProgrammeType.taught:
            raise WorkflowError("Board summary only applies to a taught programme")

        enrolments = await self.repo.enrolments_for_student(student_id)
        total = len(enrolments)
        passed = condoned = failed = pending = 0
        failed_codes: list[str] = []
        pending_codes: list[str] = []
        credits_achieved = 0
        for e in enrolments:
            module = await self.repo.get_module(e.module_id)
            code = module.code if module else "?"
            outcome = e.outcome.value if hasattr(e.outcome, "value") else str(e.outcome)
            credits_achieved += e.credits_awarded or 0
            if outcome == "passed":
                passed += 1
            elif outcome == "condoned":
                condoned += 1
            elif outcome == "failed":
                failed += 1
                failed_codes.append(code)
            else:
                pending += 1
                pending_codes.append(code)

        target = programme.taught_total_credits
        award = await self.repo.get_award(student_id)
        complete = passed + condoned

        figures: dict[str, str] = {
            "total modules": str(total),
            "modules complete": str(complete),
            "modules failed": str(failed),
            "modules awaiting marks": str(pending),
            "credits achieved": str(credits_achieved),
        }
        if target:
            figures["credits required"] = str(target)
        if award and award.classification:
            figures["projected classification"] = award.classification.value
            if award.final_mark is not None:
                figures["final mark"] = f"{float(award.final_mark):.1f}"

        recs: list[str] = []
        if failed_codes:
            recs.append(f"Resit or refer for condonement: {', '.join(failed_codes)}.")
        if pending_codes:
            recs.append(f"Awaiting marks: {', '.join(pending_codes)}.")
        if target and credits_achieved < target:
            recs.append(f"{target - credits_achieved} of {target} credits still outstanding.")
        if total and complete == total and not (award and award.classification):
            recs.append("All modules complete — compute the classification.")
        if not recs:
            recs.append("On track — no action outstanding.")

        fallback = (
            f"{complete} of {total} modules complete, {credits_achieved}"
            + (f" of {target}" if target else "") + " credits achieved"
            + (f"; {failed} to resit or condone" if failed else "")
            + (f"; {pending} awaiting marks" if pending else "")
            + (f". Projected classification: {award.classification.value}."
               if award and award.classification else ".")
        )

        from app.ai.narrate import narrate as ai_narrate
        from app.ai.types import Evidence
        from app.modules.person.models import Person

        person = await self.session.get(Person, student.person_id)
        first = person.given_name if person else "the student"

        narration = await ai_narrate(
            evidence=Evidence(figures=figures, context={"studentFirstName": first}),
            question=(
                f"Summarise for the exam board and supervisor, in one or two short sentences, "
                f"{first}'s standing on this taught programme and the single most important next "
                "action. State modules complete of the total and the credit position; if any "
                "modules failed, note they need a resit or condonement; give the projected "
                "classification if present. Only use the figures given; neutral and factual; no "
                "metaphors."
            ),
            fallback_template=fallback,
        )
        return {
            "figures": figures,
            "recommendations": recs,
            "narration": narration.body,
            "narrationSource": narration.provenance.source,
            "model": narration.provenance.model,
        }
