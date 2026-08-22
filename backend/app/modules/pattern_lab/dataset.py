"""Dataset builder (PL-1): population → labels → point-in-time features → quality report.

The builder does the preparation the administrator would otherwise need a data specialist
for (doc §2), and it does it **reproducibly**: the dataset version is a content hash, so the
same underlying data always yields the same version, and a stored dataset is a frozen
artifact discovery can be re-run against.

Leakage is handled structurally: every feature receives the target's cutoff date and
non-temporal features never run at all (see features.py). The quality report lists every
exclusion — of students and of features — with its reason, because a silently shrunk
population reads as "covered everything" when it didn't.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.modules.pattern_lab.features import FEATURES, TARGET_EXCLUSIONS, StudentCtx
from app.modules.pattern_lab.models import MlDataset
from app.modules.pattern_lab.targets import TARGETS


class DatasetBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Bulk context loading (one query per table — the cohort-integrity lesson)
    # ------------------------------------------------------------------

    async def _contexts(self) -> list[StudentCtx]:
        from app.modules.funding.models import FundingArrangement
        from app.modules.person.models import Person
        from app.modules.progression.models import Milestone
        from app.modules.student_record.models import ResearchProject, Student
        from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship

        rows = (await self.session.execute(
            select(Student, Person).join(Person, Person.id == Student.person_id)
        )).all()
        ids = [s.id for s, _ in rows]

        def by_student(items, attr="student_id"):
            out: dict[uuid.UUID, list] = {}
            for it in items:
                out.setdefault(getattr(it, attr), []).append(it)
            return out

        projects = {p.student_id: p for p in (await self.session.execute(
            select(ResearchProject).where(ResearchProject.student_id.in_(ids))
        )).scalars().unique().all()}
        milestones = by_student((await self.session.execute(
            select(Milestone).where(Milestone.student_id.in_(ids))
        )).scalars().unique().all())
        meetings = by_student((await self.session.execute(
            select(SupervisionMeeting).where(SupervisionMeeting.student_id.in_(ids))
        )).scalars().all())
        rels = by_student((await self.session.execute(
            select(SupervisorRelationship).where(SupervisorRelationship.student_id.in_(ids))
        )).scalars().all())
        arrangements = by_student((await self.session.execute(
            select(FundingArrangement).where(FundingArrangement.student_id.in_(ids))
        )).scalars().all())

        return [StudentCtx(
            student=s, person=p, project=projects.get(s.id),
            milestones=milestones.get(s.id, []), meetings=meetings.get(s.id, []),
            supervisor_rels=rels.get(s.id, []), arrangements=arrangements.get(s.id, []),
        ) for s, p in rows]

    # ------------------------------------------------------------------
    # Outcome labelling per target: (eligible?, outcome, cutoff, exclusion_reason)
    # ------------------------------------------------------------------

    def _label_progression_delay(self, ctx: StudentCtx, min_gap: int):
        # "Delayed" has two real shapes in the data: a milestone decided after its due date,
        # and — the common one — a milestone past its due date with **no decision at all**.
        # The `overdue` status enum value is never actually set; overdue is a fact about
        # dates, not a stored status. (Found by running discovery on the live cohort: the
        # status-based version labelled 0 of 341 students positive against 36 planted.)
        dues = sorted(m.due_date for m in ctx.milestones if m.due_date)
        if not dues:
            return None, None, "no milestone schedule"
        cutoff = dues[0]
        today = date.today()
        resolved, late = False, False
        for m in ctx.milestones:
            status = m.status.value if hasattr(m.status, "value") else str(m.status)
            decided_at = m.review.decided_at if m.review else None
            if status == "decided":
                resolved = True
                if decided_at and m.due_date and decided_at.date() > m.due_date:
                    late = True
            elif m.due_date and m.due_date < today:
                resolved, late = True, True          # past due, still undecided
        if not resolved:
            return None, None, "no milestone resolved yet — outcome not knowable"
        return late, cutoff, None

    def _label_funding_continuity(self, ctx: StudentCtx, min_gap: int):
        start = ctx.student.start_date
        if start is None or not ctx.arrangements:
            return None, None, "no funding history"
        cutoff = start + timedelta(days=90)
        if date.today() < cutoff:
            return None, None, "fewer than 90 days of history"
        spans = sorted([(a.valid_from, a.valid_to) for a in ctx.arrangements if a.valid_from])
        gaps = []       # (gap_begin, gap_days)
        prev_end = start
        for vf, vt in spans:
            if prev_end and vf > prev_end:
                gaps.append((prev_end, (vf - prev_end).days))
            if vt is None:
                prev_end = None
                break
            prev_end = max(prev_end, vt) if prev_end else vt
        if prev_end and prev_end < date.today():
            gaps.append((prev_end, (date.today() - prev_end).days))
        # Only gaps that BEGAN after the prediction point count — an earlier gap would be
        # known at the cutoff, and predicting the known is leakage by definition.
        outcome = any(begin >= cutoff and days > min_gap for begin, days in gaps)
        return outcome, cutoff, None

    def _label(self, target_key: str, ctx: StudentCtx, min_gap: int):
        if target_key == "progression_delay":
            return self._label_progression_delay(ctx, min_gap)
        if target_key == "funding_continuity":
            return self._label_funding_continuity(ctx, min_gap)
        raise ValidationAppError(
            f"'{TARGETS[target_key].label}' is defined but not yet buildable — "
            "its outcome data does not exist in this installation."
        )

    # ------------------------------------------------------------------
    # Sufficiency + build
    # ------------------------------------------------------------------

    async def sufficiency(self, target_key: str) -> dict:
        """The gate: is there enough labelled data for this target to be analysed at all?"""
        from app.modules.settings.service import setting_value

        t = TARGETS.get(target_key)
        if t is None:
            raise NotFoundError(f"Unknown target: {target_key}")
        if target_key in ("completion_forecast", "applicant_outcome"):
            # Buildable labelling for these arrives when the data exists; report why locked.
            from app.modules.completion.models import Completion
            from sqlalchemy import func
            n = (await self.session.execute(
                select(func.count()).select_from(Completion)
            )).scalar_one() if target_key == "completion_forecast" else None
            reason = (f"{n} completion(s) recorded; at least {t.min_eligible} needed"
                      if target_key == "completion_forecast"
                      else "conversion is ~99.7% — there is almost no negative class to learn from")
            return {"target": target_key, "eligible": 0, "positives": 0, "negatives": 0,
                    "sufficient": False, "reason": reason}

        min_gap = await setting_value(self.session, "funding.min_gap_days")
        eligible = positives = 0
        for ctx in await self._contexts():
            outcome, _, excl = self._label(target_key, ctx, min_gap)
            if excl is None:
                eligible += 1
                positives += int(bool(outcome))
        negatives = eligible - positives
        ok = (eligible >= t.min_eligible and min(positives, negatives) >= t.min_minority)
        return {"target": target_key, "eligible": eligible, "positives": positives,
                "negatives": negatives, "sufficient": ok,
                "reason": None if ok else
                f"needs ≥{t.min_eligible} eligible and ≥{t.min_minority} in the smaller class "
                f"(have {eligible} eligible, smaller class {min(positives, negatives)})"}

    async def build(self, target_key: str, created_by: uuid.UUID | None) -> MlDataset:
        from app.modules.settings.service import setting_value

        t = TARGETS.get(target_key)
        if t is None:
            raise NotFoundError(f"Unknown target: {target_key}")
        min_gap = await setting_value(self.session, "funding.min_gap_days")

        contexts = await self._contexts()
        excluded_features = [
            {"key": f.key, "label": f.label, "reason": f.exclude_reason or "not temporal"}
            for f in FEATURES if not f.temporal
        ] + [
            {"key": k, "label": next(f.label for f in FEATURES if f.key == k), "reason": why}
            for k, why in TARGET_EXCLUSIONS.get(target_key, {}).items()
        ]
        excluded_keys = {e["key"] for e in excluded_features}
        active = [f for f in FEATURES if f.key not in excluded_keys]

        rows, exclusions = [], {}
        positives = 0
        for ctx in contexts:
            outcome, cutoff, excl = self._label(target_key, ctx, min_gap)
            if excl is not None:
                exclusions[excl] = exclusions.get(excl, 0) + 1
                continue
            feats = {}
            for f in active:
                v = f.compute(ctx, cutoff)
                feats[f.key] = (float(v) if isinstance(v, bool) is False and v is not None
                                else (1.0 if v is True else (0.0 if v is False else None)))
            positives += int(bool(outcome))
            rows.append({"studentId": str(ctx.student.id), "outcome": int(bool(outcome)),
                         "cutoff": cutoff.isoformat(), "features": feats})

        completeness = {
            f.key: (round(sum(1 for r in rows if r["features"].get(f.key) is not None)
                          / len(rows), 3) if rows else 0.0)
            for f in active
        }
        eligible, negatives = len(rows), len(rows) - positives
        sufficient = (eligible >= t.min_eligible
                      and min(positives, negatives) >= t.min_minority)

        version = hashlib.sha256(json.dumps(
            {"target": target_key, "features": sorted(f.key for f in active), "rows": rows},
            sort_keys=True).encode()).hexdigest()[:16]

        ds = MlDataset(
            target_key=target_key,
            name=f"{t.label} — {date.today().isoformat()}",
            version=version, status="built" if sufficient else "insufficient",
            records_found=len(contexts), eligible=eligible, positives=positives,
            sufficient=sufficient,
            quality={
                "exclusions": [{"reason": k, "count": v} for k, v in sorted(exclusions.items())],
                "completeness": completeness,
                "excludedFeatures": excluded_features,
                "activeFeatures": [
                    {"key": f.key, "group": f.group, "label": f.label,
                     "description": f.description} for f in active],
                "predictionPoint": t.prediction_point,
            },
            matrix=rows, created_by_user_id=created_by,
        )
        self.session.add(ds)
        await self.session.commit()
        await self.session.refresh(ds)
        return ds
