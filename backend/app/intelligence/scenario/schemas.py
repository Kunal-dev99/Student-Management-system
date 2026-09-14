"""Scenario schemas — deterministic diff + model sensitivity, kept strictly separate.

Rule from arch §10: "These two outputs must stay separate all the way to the frontend."
Both live on the same envelope but under different fields; the UI must not average or
mix them.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel


class ScenarioRequest(BaseModel):
    student_id: uuid.UUID
    change: Literal[
        "suspend_for_weeks",
        "extend_expected_end_by_months",
        "change_study_mode",
        "shift_next_milestone_by_days",
    ]
    params: dict[str, Any]
    """e.g. {"weeks": 12} for suspend, {"months": 6} for extend, {"mode": "part_time"}."""

    include_sensitivity: bool = False
    """If true, and Pattern Lab is available, also compute non-causal model sensitivity."""


class DeterministicDiff(BaseModel):
    """Rule-computed impact — dates move, funding coverage shifts, tasks re-plan."""
    expected_end_before: date | None = None
    expected_end_after: date | None = None
    milestones_shifted: list[dict[str, Any]] = []
    funding_coverage_before: dict[str, Any] = {}
    funding_coverage_after: dict[str, Any] = {}
    assumptions: list[str] = []


class ModelSensitivity(BaseModel):
    """Non-causal — how a production model's score responds to a change in inputs.

    Quantitative: computed by re-running the model's exact production pipeline with
    the changed inputs. Populated once the SensitivityRunner adapter is wired to
    `MlModelVersion.artifact` (tracked separately). Until then this stays empty and
    `qualitative_sensitivity` below is what fills the gap — never fabricated numbers.
    """
    target: str
    baseline_probability: float
    sensitivity_probability: float
    delta_pp: float
    model_version_id: uuid.UUID | None = None
    note: str = "Model sensitivity, not predicted intervention effect."


class QualitativeSensitivity(BaseModel):
    """LLM-judged qualitative direction — the fallback when no quantitative model
    sensitivity pipeline exists yet for a target this student has a live score on.

    Deliberately NOT a probability. A direction + one-sentence rationale, always
    labelled with its engine so the reader can never mistake it for a re-run of the
    trained model.
    """
    target: str
    direction: Literal["likely_increase", "likely_decrease", "no_clear_change", "uncertain"]
    rationale: str
    baseline_probability: float | None = None
    engine: str = "fallback"
    model: str | None = None
    note: str = "Qualitative judgment from the LLM, not a re-run of the trained model."


class ScenarioResult(BaseModel):
    student_id: uuid.UUID
    request: ScenarioRequest
    deterministic_diff: DeterministicDiff
    model_sensitivity: list[ModelSensitivity] = []
    qualitative_sensitivity: list[QualitativeSensitivity] = []
    missing_data: list[str] = []
    computed_at: datetime
