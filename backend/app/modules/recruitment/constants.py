"""Recruitment enumerations and state machines (arch §8.2, §8.4)."""
from __future__ import annotations

import enum


class OpportunityStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    open = "open"
    recruiting = "recruiting"
    filled = "filled"
    closed = "closed"


class ApplicationRoute(str, enum.Enum):
    opportunity_led = "opportunity_led"
    student_led = "student_led"


class CandidateStage(str, enum.Enum):
    prospect = "prospect"
    applicant = "applicant"
    under_assessment = "under_assessment"
    shortlisted = "shortlisted"
    interview = "interview"
    selected = "selected"
    offer_made = "offer_made"
    offer_accepted = "offer_accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"
    converted = "converted"


# Allowed opportunity transitions (arch §8.4): draft -> approved -> open -> recruiting -> filled -> closed.
OPPORTUNITY_TRANSITIONS: dict[OpportunityStatus, set[OpportunityStatus]] = {
    OpportunityStatus.draft: {OpportunityStatus.approved, OpportunityStatus.closed},
    OpportunityStatus.approved: {OpportunityStatus.open, OpportunityStatus.closed},
    OpportunityStatus.open: {OpportunityStatus.recruiting, OpportunityStatus.closed},
    OpportunityStatus.recruiting: {OpportunityStatus.filled, OpportunityStatus.closed},
    OpportunityStatus.filled: {OpportunityStatus.closed},
    OpportunityStatus.closed: set(),
}

# Terminal stages an application cannot advance out of.
TERMINAL_STAGES = {CandidateStage.rejected, CandidateStage.withdrawn, CandidateStage.converted}
