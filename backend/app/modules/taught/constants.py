"""Taught-lifecycle enumerations (ICR G1).

Kept deliberately small for the MVP slice: assessment kinds, a module-enrolment status, and a
classification band. Grading bands vary by institution, so ``ClassificationBand`` is only the
canonical UK-MSc set — the mapping from marks to band lives in the service as configurable policy,
never hard-coded to ICR's thresholds.
"""
from __future__ import annotations

import enum


class AssessmentType(str, enum.Enum):
    essay = "essay"
    exam = "exam"
    coursework = "coursework"
    presentation = "presentation"
    dissertation = "dissertation"


class ModuleEnrolmentStatus(str, enum.Enum):
    enrolled = "enrolled"
    completed = "completed"
    withdrawn = "withdrawn"
    failed = "failed"


class ModuleOutcome(str, enum.Enum):
    """The academic outcome of a module once its assessments are marked.

    ``pending`` = not all components marked yet; ``pass`` = module mark >= pass mark;
    ``condoned`` = below pass mark but condoned by the board (credits still awarded, within the
    programme's condonement allowance); ``fail`` = below pass mark and not condoned.
    """
    pending = "pending"
    passed = "passed"
    condoned = "condoned"
    failed = "failed"


# Default UK-MSc grading policy. Per-programme overrides live in Programme.grading_policy (JSON);
# nothing here is hard-coded into logic — the service reads the merged policy.
DEFAULT_GRADING_POLICY: dict = {
    "passMark": 50,          # module pass mark (%)
    "resitCap": 50,          # a resit mark is capped at this
    "condonementCredits": 30,  # total failed credits the board may condone
    "distinctionMark": 70,   # award classification thresholds (credit-weighted final %)
    "meritMark": 60,
    "passMarkAward": 50,
}


class ClassificationBand(str, enum.Enum):
    """Award classification for a taught programme (credit-weighted).

    Canonical UK taught-postgraduate set. The mark -> band thresholds are policy (Settings), not
    baked into this enum, so another institution can use different cut-offs against the same bands.
    """
    distinction = "distinction"
    merit = "merit"
    pass_ = "pass"
    fail = "fail"
