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


class PanelRole(str, enum.Enum):
    chair = "chair"
    internal_assessor = "internal_assessor"
    independent_assessor = "independent_assessor"
    supervisor_observer = "supervisor_observer"


class AppealStatus(str, enum.Enum):
    submitted = "submitted"
    under_review = "under_review"
    upheld = "upheld"
    rejected = "rejected"
    withdrawn = "withdrawn"


# Phase 4B.6 — a valid panel needs a chair and an assessor independent of the supervisory team.
REQUIRED_PANEL_ROLES = {PanelRole.chair, PanelRole.independent_assessor}

# Outcomes that require conditions + a scheduled re-review.
CONDITIONAL_OUTCOMES = {
    ProgressionOutcome.progress_with_conditions,
    ProgressionOutcome.further_review,
}

# Default window for a conditions re-review, and the appeal window after a decision.
RE_REVIEW_DAYS = 90
APPEAL_WINDOW_DAYS = 14
