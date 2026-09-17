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
    "resitCap": 50,          # flat resit cap — applies to every attempt >= 2 when the ladder is unset
    # A DEGRADING resit ladder — each subsequent attempt gets a harsher cap. Index 0 is the
    # cap for attempt 2, index 1 for attempt 3, and so on. Beyond the list length the LAST value
    # is used (the harshest). When unset (None), the flat `resitCap` above applies to every resit.
    # Example: [50, 40, 30] → attempt 2 capped at 50, attempt 3 at 40, attempt 4+ at 30.
    "resitCapLadder": None,
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
