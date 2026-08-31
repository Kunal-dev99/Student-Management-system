"""ICR module — additive configuration only.

Encodes the Institute of Cancer Research PGR model into the EXISTING engines:
the strict 4-year progression system becomes milestone definitions on two new
programmes (non-clinical PhD, clinical MD(Res)), and the ICR funder landscape
becomes funding sources. No application code is touched — the progression
generator, panels, appeals, funding and statutory machinery all work on these
rows exactly as they do for every other programme.

Idempotent — safe to re-run (existing ICR rows are left alone).

    python -m scripts.seed_icr
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import SessionFactory
from app.modules.funding.models import FundingSource
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.models import Department, Programme

DEPT = ("ICR", "Institute of Cancer Research")

# programme code -> (name, [(milestone name, due_offset_days, extras), ...])
PROGRAMMES = {
    "ICR-PHD": (
        "ICR PhD — Non-Clinical (4-year)",
        [
            ("Induction & Lab Safety Review", 30, {
                "assessment_criteria": {"focus": ["onboarding complete", "technical training plan",
                                                  "lab safety certification", "baseline data plan"]},
            }),
            ("Transfer Viva — MPhil to PhD Upgrade", 365, {
                "required_documents": {"upgradeReport":
                    "2,000-3,000 words: preliminary findings, comprehensive literature review, "
                    "explicit roadmap for the remaining project"},
                "review_panel": {"composition": ["primary supervisor", "co-supervisor",
                                                 "independent internal academic assessor"]},
                "assessment_criteria": {"gate":
                    "Registration is upgraded from provisional MPhil to PhD only on a successful defence. "
                    "The most crucial filter in the system."},
                # ICR gap 1 — automatic registration_status flip on decide.
                "registration_effect": {
                    "onDecideContinue": "PhD (upgraded)",
                    "onDecideFail":     "Withdrawn (transfer viva failed)",
                },
            }),
            ("24-Month Progress Review", 730, {
                "review_panel": {"composition": ["ICR Academic Committee"]},
            }),
            ("30-Month Data Barrier Review", 913, {
                "assessment_criteria": {"gate":
                    "Sufficient raw, novel data to form a viable thesis — minimises the risk of "
                    "project failure in the final stretch."},
            }),
            ("Final Thesis Submission (48-month limit)", 1460, {
                "required_documents": {"thesis": "Definitive research thesis, up to 100,000 words"},
                "review_panel": {"composition": ["internal examiner",
                                                 "at least one external expert examiner"]},
            }),
        ],
    ),
    "ICR-MDRES": (
        "ICR MD(Res) — Clinical (2-3 year)",
        [
            ("Induction & Clinical-Academic Plan Review", 30, {
                "assessment_criteria": {"focus": [
                    "integration with Specialist Registrar training confirmed",
                    "translational project scope agreed"]},
            }),
            ("12-Month Progress Review", 365, {
                "review_panel": {"composition": ["primary supervisor", "clinical co-supervisor",
                                                 "independent tutor"]},
            }),
            ("24-Month Progress Review", 730, {
                "review_panel": {"composition": ["ICR Academic Committee"]},
            }),
            ("Final Thesis Submission (36-month limit)", 1095, {
                "required_documents": {"thesis": "Research thesis for the MD(Res) award"},
                "review_panel": {"composition": ["internal examiner", "external expert examiner"]},
            }),
        ],
    ),
}

# The ICR funder landscape — additive rows in the existing funding_source table.
FUNDERS = [
    ("Cancer Research UK (CRUK)", "charity"),
    ("Medical Research Council (MRC)", "research_council"),
    ("Breast Cancer Now", "charity"),
    ("ICR Corporate Partnership Pool", "industry"),
]


async def main() -> None:
    async with SessionFactory() as s:
        dept = (await s.execute(select(Department).where(Department.code == DEPT[0]))).scalars().first()
        if dept is None:
            dept = Department(code=DEPT[0], name=DEPT[1])
            s.add(dept)
            await s.flush()
            print(f"  + department {DEPT[1]}")

        for code, (name, milestones) in PROGRAMMES.items():
            prog = (await s.execute(select(Programme).where(Programme.code == code))).scalars().first()
            if prog is not None:
                print(f"  = programme {code} already present — skipped")
                continue
            prog = Programme(code=code, name=name, department_id=dept.id)
            s.add(prog)
            await s.flush()
            for mname, offset, extras in milestones:
                s.add(MilestoneDefinition(
                    programme_id=prog.id, name=mname, due_offset_days=offset,
                    required_documents=extras.get("required_documents"),
                    review_panel=extras.get("review_panel"),
                    assessment_criteria=extras.get("assessment_criteria"),
                    registration_effect=extras.get("registration_effect"),
                ))
            print(f"  + programme {name} with {len(milestones)} milestone definitions")

        existing = {f.name for f in (await s.execute(select(FundingSource))).scalars().all()}
        for fname, ftype in FUNDERS:
            if fname in existing:
                print(f"  = funder {fname} already present — skipped")
                continue
            s.add(FundingSource(name=fname, funder_type=ftype))
            print(f"  + funding source {fname}")

        await s.commit()
        print("ICR seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
