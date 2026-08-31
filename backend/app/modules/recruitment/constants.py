"""Recruitment enumerations and state machines (arch §8.2, §8.4)."""
from __future__ import annotations

import enum


class OpportunityStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    open = "open"
    recruiting = "recruiting"
    # W1.3 — paused is a temporary hold that keeps the opportunity intact (positions, applications
    # already in flight) but stops it accepting new assessments/offers. open <-> paused are the only
    # transitions in and out.
    paused = "paused"
    filled = "filled"
    closed = "closed"


# W1.1 — an opportunity is either fully funded (stipend + fees), partially funded, or unfunded.
# Before this the platform inferred the split from stipend_amount being set or null; making it
# explicit lets the recruitment pipeline filter and lets the offer flow decide what to advertise.
class OpportunityFunding(str, enum.Enum):
    funded = "funded"
    partially_funded = "partially_funded"
    unfunded = "unfunded"


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
    # W1.3 — paused is bidirectional with open only. From paused you resume (→open) or close.
    OpportunityStatus.open: {OpportunityStatus.recruiting, OpportunityStatus.paused, OpportunityStatus.closed},
    OpportunityStatus.paused: {OpportunityStatus.open, OpportunityStatus.closed},
    OpportunityStatus.recruiting: {OpportunityStatus.filled, OpportunityStatus.paused, OpportunityStatus.closed},
    OpportunityStatus.filled: {OpportunityStatus.closed},
    OpportunityStatus.closed: set(),
}

# Terminal stages an application cannot advance out of.
TERMINAL_STAGES = {CandidateStage.rejected, CandidateStage.withdrawn, CandidateStage.converted}
