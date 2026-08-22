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
    independent_chair = "independent_chair"


class VivaFormat(str, enum.Enum):
    in_person = "in_person"
    online = "online"
    hybrid = "hybrid"


class CorrectionKind(str, enum.Enum):
    minor = "minor"
    major = "major"


# Statutory-ish correction windows (days) from the viva. Minor: 4 weeks; major: 6 months.
CORRECTION_DEADLINE_DAYS = {
    CorrectionKind.minor: 28,
    CorrectionKind.major: 182,
}


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

# Outcomes that open a corrections period, and the correction kind they create.
OUTCOME_TO_CORRECTION_KIND = {
    ExaminationOutcome.pass_with_corrections: CorrectionKind.minor,
    ExaminationOutcome.major_corrections: CorrectionKind.major,
}
