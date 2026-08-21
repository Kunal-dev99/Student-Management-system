"""Thesis and examination enumerations (arch §8.2, §8.10)."""
from __future__ import annotations

import enum


class ThesisStatus(str, enum.Enum):
    preparation = "preparation"
    intention_to_submit = "intention_to_submit"
    submitted = "submitted"
    under_examination = "under_examination"
    corrections = "corrections"
    resubmission = "resubmission"
    approved = "approved"
    failed = "failed"


class ExaminerType(str, enum.Enum):
    internal = "internal"
    external = "external"


class ExaminationOutcome(str, enum.Enum):
    pass_ = "pass"
    pass_with_corrections = "pass_with_corrections"
    major_corrections = "major_corrections"
    resubmission = "resubmission"
    fail = "fail"


# Map an examination outcome to the resulting thesis status.
OUTCOME_TO_THESIS_STATUS = {
    ExaminationOutcome.pass_: ThesisStatus.approved,
    ExaminationOutcome.pass_with_corrections: ThesisStatus.corrections,
    ExaminationOutcome.major_corrections: ThesisStatus.corrections,
    ExaminationOutcome.resubmission: ThesisStatus.resubmission,
    ExaminationOutcome.fail: ThesisStatus.failed,
}
