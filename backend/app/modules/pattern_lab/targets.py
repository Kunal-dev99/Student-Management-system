"""Governed analysis targets (Pattern Lab PL-1, plan §5).

Training and discovery are only possible against targets defined HERE — there is no
"predict anything" (product guardrail §13: no uncontrolled arbitrary model training).
A target owns:

- the business question and outcome definition, in plain language;
- the **population** and **eligibility** rules (who can be labelled at all);
- the **prediction point** semantics — the date before which features must be knowable,
  which is what makes leakage prevention structural rather than a review step;
- the **sufficiency gate**: minimum eligible outcomes and minimum minority-class count
  before discovery/training is even offered. Measured against the live data, two of the
  four launch targets do not pass today (1 completion; 99.7% conversion) — they stay
  visible but locked, and the UI says exactly what is missing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetDef:
    key: str
    label: str
    question: str                 # the institutional question, verbatim UI copy
    outcome_label: str            # what "1" means, in business language
    outcome_definition: str       # exact rule, in plain language
    population: str
    prediction_point: str         # plain-language statement of the temporal cutoff
    min_eligible: int = 50        # eligible labelled rows required
    min_minority: int = 15        # smallest class must have at least this many


TARGETS: dict[str, TargetDef] = {t.key: t for t in [
    TargetDef(
        key="progression_delay",
        label="Progression Delay Risk",
        question="What factors are associated with progression delays?",
        outcome_label="experienced a progression delay",
        outcome_definition=(
            "At least one progression milestone was decided after its due date, or is past "
            "its due date with no decision recorded. Students with no decided and no "
            "past-due milestone are excluded — their outcome is not yet knowable."
        ),
        population="Students with at least one milestone that is decided or overdue.",
        prediction_point=(
            "The student's first milestone due date. Every feature is computed only from "
            "records dated strictly before that day — what the institution could have known "
            "when the first milestone fell due."
        ),
    ),
    TargetDef(
        key="funding_continuity",
        label="Funding Continuity Risk",
        question="What patterns are associated with funding disruption?",
        outcome_label="experienced a funding gap",
        outcome_definition=(
            "A gap longer than the institution's funding gap tolerance (a Phase 8 setting) "
            "between consecutive funding arrangements, or between registration and the first "
            "arrangement, beginning more than 90 days after the student started."
        ),
        population="Students with at least one funding arrangement and 90+ days of history.",
        prediction_point=(
            "90 days after the student's start date. Gaps that had already begun by then are "
            "excluded from the outcome (they would be known, not predicted), and features "
            "use only records dated before that day."
        ),
    ),
    TargetDef(
        key="completion_forecast",
        label="Completion Forecast",
        question="Which factors are associated with delayed completion?",
        outcome_label="completed later than the expected end date",
        outcome_definition="Completion recorded after the student's expected end date.",
        population="Students with a recorded completion.",
        prediction_point="Twelve months before the expected end date.",
    ),
    TargetDef(
        key="applicant_outcome",
        label="Applicant Outcome",
        question="Which application characteristics are associated with successful "
                 "progression to registration?",
        outcome_label="progressed from application to registered student",
        outcome_definition="The application reached a registered student record.",
        population="Applications with a terminal outcome (registered, rejected or withdrawn).",
        prediction_point="Application submission.",
    ),
]}


def target_out(t: TargetDef) -> dict:
    return {
        "key": t.key, "label": t.label, "question": t.question,
        "outcomeLabel": t.outcome_label, "outcomeDefinition": t.outcome_definition,
        "population": t.population, "predictionPoint": t.prediction_point,
        "minEligible": t.min_eligible, "minMinority": t.min_minority,
    }
