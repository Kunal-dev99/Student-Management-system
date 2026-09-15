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


class ClassificationBand(str, enum.Enum):
    """Award classification for a taught programme (credit-weighted).

    Canonical UK taught-postgraduate set. The mark -> band thresholds are policy (Settings), not
    baked into this enum, so another institution can use different cut-offs against the same bands.
    """
    distinction = "distinction"
    merit = "merit"
    pass_ = "pass"
    fail = "fail"
