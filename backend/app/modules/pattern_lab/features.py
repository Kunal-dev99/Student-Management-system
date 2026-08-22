"""Feature registry (Pattern Lab PL-1).

Every candidate signal is defined here with its **temporal semantics declared**. A feature
computes from a per-student context and a `cutoff` date (the target's prediction point) and
must only use records dated strictly before the cutoff. Features that cannot honour a cutoff
are declared `temporal=False` and are **structurally excluded** from every dataset — they
appear in the quality report as excluded, with the reason, so the exclusion is visible
rather than silent (plan §5: leakage prevention is structural).

The context (`StudentCtx`) is bulk-loaded once per dataset build — the cohort-integrity
lesson (O(students × queries) measured at 1.2–1.9 s) applied from the start.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable


@dataclass
class StudentCtx:
    """Everything a feature may look at, bulk-loaded per student."""
    student: Any
    person: Any
    project: Any | None = None
    milestones: list = field(default_factory=list)          # with .due_date
    meetings: list = field(default_factory=list)            # with .met_on
    supervisor_rels: list = field(default_factory=list)     # with .valid_from/.valid_to
    arrangements: list = field(default_factory=list)        # with .valid_from/.valid_to


@dataclass(frozen=True)
class FeatureDef:
    key: str
    group: str            # Research | Supervision | Progression | Funding | Student
    label: str
    description: str
    temporal: bool        # True = respects the cutoff; False = structurally excluded
    compute: Callable[[StudentCtx, date], float | int | bool | None]
    exclude_reason: str | None = None   # set on temporal=False features


def _days(a: date | None, b: date | None) -> int | None:
    return (b - a).days if a and b else None


# ----------------------------------------------------------------------------------
# Feature computations. `cutoff` is exclusive: use records dated strictly before it.
# ----------------------------------------------------------------------------------

def _meetings_before(ctx: StudentCtx, cutoff: date):
    return sum(1 for m in ctx.meetings if m.met_on and m.met_on < cutoff)

def _days_since_last_meeting(ctx: StudentCtx, cutoff: date):
    dates = [m.met_on for m in ctx.meetings if m.met_on and m.met_on < cutoff]
    return (cutoff - max(dates)).days if dates else None

def _supervisors_at(ctx: StudentCtx, cutoff: date):
    return sum(1 for r in ctx.supervisor_rels
               if r.valid_from and r.valid_from < cutoff
               and (r.valid_to is None or r.valid_to >= cutoff))

def _supervisor_change_before(ctx: StudentCtx, cutoff: date):
    return any(r.valid_to and r.valid_to < cutoff for r in ctx.supervisor_rels)

def _part_time(ctx: StudentCtx, cutoff: date):
    mode = getattr(ctx.student, "study_mode", None)
    if mode is None:
        return None
    return (mode.value if hasattr(mode, "value") else str(mode)) == "part_time"

def _days_start_to_first_due(ctx: StudentCtx, cutoff: date):
    dues = sorted(m.due_date for m in ctx.milestones if m.due_date)
    return _days(ctx.student.start_date, dues[0]) if dues and ctx.student.start_date else None

def _has_project(ctx: StudentCtx, cutoff: date):
    return ctx.project is not None

def _project_linked_to_award(ctx: StudentCtx, cutoff: date):
    return bool(ctx.project is not None and getattr(ctx.project, "research_award_id", None))

def _arrangements_before(ctx: StudentCtx, cutoff: date):
    return sum(1 for a in ctx.arrangements if a.valid_from and a.valid_from < cutoff)

def _funded_at_cutoff(ctx: StudentCtx, cutoff: date):
    return any(a.valid_from and a.valid_from < cutoff
               and (a.valid_to is None or a.valid_to >= cutoff)
               for a in ctx.arrangements)

def _funding_started_late(ctx: StudentCtx, cutoff: date):
    starts = [a.valid_from for a in ctx.arrangements if a.valid_from and a.valid_from < cutoff]
    if not starts or not ctx.student.start_date:
        return None
    return (min(starts) - ctx.student.start_date).days > 7

def _stipend_at_cutoff(ctx: StudentCtx, cutoff: date):
    live = [a for a in ctx.arrangements
            if a.valid_from and a.valid_from < cutoff
            and (a.valid_to is None or a.valid_to >= cutoff) and a.stipend_amount]
    return float(max(a.stipend_amount for a in live)) if live else None

def _funding_award_linked(ctx: StudentCtx, cutoff: date):
    return any(a.valid_from and a.valid_from < cutoff and a.research_award_id
               for a in ctx.arrangements)

def _milestone_count_defined(ctx: StudentCtx, cutoff: date):
    # Due dates are set at registration — schedule *shape* is knowable upfront.
    return len(ctx.milestones)

def _total_decided_ever(ctx: StudentCtx, cutoff: date):
    return None  # never computed — declared non-temporal below


FEATURES: list[FeatureDef] = [
    # --- Student ---
    FeatureDef("part_time", "Student", "Part-time study mode",
               "Registered study mode at the prediction point.", True, _part_time),
    # --- Supervision ---
    FeatureDef("meetings_before", "Supervision", "Supervision meetings held",
               "Meetings recorded before the prediction point.", True, _meetings_before),
    FeatureDef("days_since_last_meeting", "Supervision", "Days since last meeting",
               "Gap between the last recorded meeting and the prediction point.",
               True, _days_since_last_meeting),
    FeatureDef("supervisors_current", "Supervision", "Current supervisors",
               "Active supervisor relationships at the prediction point.", True, _supervisors_at),
    FeatureDef("supervisor_change", "Supervision", "Supervisor change occurred",
               "A supervisor relationship ended before the prediction point.",
               True, _supervisor_change_before),
    # --- Progression ---
    FeatureDef("milestones_defined", "Progression", "Milestones scheduled",
               "Milestones on the student's schedule (set at registration).",
               True, _milestone_count_defined),
    FeatureDef("days_to_first_due", "Progression", "Days from start to first milestone",
               "How long the schedule allows before the first milestone.",
               True, _days_start_to_first_due),
    FeatureDef("milestones_decided_total", "Progression", "Total milestones ever decided",
               "Lifetime count of decided milestones.", False, _total_decided_ever,
               exclude_reason="Counts decisions made after the prediction point — this IS the "
                              "outcome, not a predictor of it."),
    # --- Funding ---
    FeatureDef("funded_at_cutoff", "Funding", "Funding active",
               "An arrangement covers the prediction point.", True, _funded_at_cutoff),
    FeatureDef("arrangements_before", "Funding", "Funding arrangements",
               "Arrangements that began before the prediction point.", True, _arrangements_before),
    FeatureDef("funding_started_late", "Funding", "Funding started late",
               "First arrangement began more than 7 days after registration.",
               True, _funding_started_late),
    FeatureDef("stipend_amount", "Funding", "Stipend amount",
               "Largest live stipend at the prediction point.", True, _stipend_at_cutoff),
    FeatureDef("funding_award_linked", "Funding", "Funding linked to an award",
               "Any early arrangement is attributed to a research award.",
               True, _funding_award_linked),
    # --- Research ---
    FeatureDef("has_project", "Research", "Research project recorded",
               "A research project row exists.", True, _has_project),
    FeatureDef("project_award_linked", "Research", "Project linked to an award",
               "The project is attributed to a research award.", True, _project_linked_to_award),
]

# Per-target structural exclusions beyond temporal rules: features whose value trivially
# encodes the target's own outcome are removed for that target, and listed in the quality
# report with this reason.
TARGET_EXCLUSIONS: dict[str, dict[str, str]] = {
    "funding_continuity": {
        "funded_at_cutoff": "Directly encodes early funding coverage — near-tautological "
                            "for a funding-gap outcome.",
        "funding_started_late": "A late funding start is itself a funding gap.",
    },
}
