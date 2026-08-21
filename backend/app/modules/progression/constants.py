"""Progression enumerations (arch §8.2, §8.8)."""
from __future__ import annotations

import enum


class MilestoneStatus(str, enum.Enum):
    not_started = "not_started"
    due = "due"
    submitted = "submitted"
    under_review = "under_review"
    decided = "decided"
    overdue = "overdue"


class ProgressionOutcome(str, enum.Enum):
    progress = "progress"
    progress_with_conditions = "progress_with_conditions"
    further_review = "further_review"
    transfer_award = "transfer_award"
    withdraw = "withdraw"
    terminate = "terminate"


# Outcomes that let the student continue → the next milestone is generated on decision.
CONTINUING_OUTCOMES = {ProgressionOutcome.progress, ProgressionOutcome.progress_with_conditions}
