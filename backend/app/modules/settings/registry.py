"""The catalogue of every institution-tunable setting (Phase 8).

Adding a setting means adding an entry here — the API, the validation, and the Settings UI all
read this registry, so there is exactly one place where a setting is defined. Defaults are the
constants the platform shipped with; the registry *references* them rather than copying the
number, so code that still imports the constant and the settings screen can never disagree
about what the default is.

Deliberately NOT here:
- SMTP credentials and the database URL — secrets and infrastructure stay in the environment
  (`backend/.env`), never in a table an API can read back out.
- Enum value sets (student status, funding type, …) — those are *domain vocabulary* with code
  attached to each value; renaming one from a settings screen would orphan the logic behind it.
  They are exposed read-only via `/reference/value-sets` so administrators can see them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.funding.constants import MIN_GAP_DAYS
from app.modules.student_record.constants import PART_TIME_FACTOR
from app.modules.supervision.constants import (
    EXPECTED_MEETING_INTERVAL_DAYS,
    MAX_SUPERVISEES_DEFAULT,
)


@dataclass(frozen=True)
class SettingDef:
    key: str
    group: str
    label: str
    description: str
    type: str                     # "int" | "float" | "bool" | "str"
    default: Any
    min: float | None = None
    max: float | None = None

    def validate(self, value: Any) -> Any:
        """Coerce and range-check a candidate value; raise ValueError with a human message."""
        if self.type == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self.label} must be true or false")
            return value
        if self.type == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                raise ValueError(f"{self.label} must be a whole number")
            value = int(value)
        elif self.type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{self.label} must be a number")
            value = float(value)
        elif self.type == "str":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{self.label} must be non-empty text")
            return value.strip()
        if self.min is not None and value < self.min:
            raise ValueError(f"{self.label} must be at least {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"{self.label} must be at most {self.max}")
        return value


SETTINGS: dict[str, SettingDef] = {s.key: s for s in [
    # --- Supervision policy ---
    SettingDef(
        key="supervision.max_supervisees", group="Supervision policy",
        label="Maximum supervisees per supervisor",
        description="A supervisor at this many current supervisees is flagged at capacity: new "
                    "primary assignments warn, and matching scores them down (never hides them).",
        type="int", default=MAX_SUPERVISEES_DEFAULT, min=1, max=50,
    ),
    SettingDef(
        key="supervision.expected_meeting_interval_days", group="Supervision policy",
        label="Expected days between supervision meetings",
        description="A student whose last recorded meeting is older than this shows as overdue "
                    "on the supervision screen, Enterprise 360 and the risk indicators.",
        type="int", default=EXPECTED_MEETING_INTERVAL_DAYS, min=7, max=365,
    ),
    # --- Student lifecycle ---
    SettingDef(
        key="lifecycle.part_time_factor", group="Student lifecycle",
        label="Part-time duration factor",
        description="Switching study mode rescales the remaining registration period by this "
                    "factor (2.0 = part-time takes twice as long). Applies to future mode "
                    "changes only; past recalculations are never rewritten.",
        type="float", default=PART_TIME_FACTOR, min=1.0, max=4.0,
    ),
    # --- Funding integrity ---
    SettingDef(
        key="funding.min_gap_days", group="Funding integrity",
        label="Funding gap tolerance (days)",
        description="Gaps between funding arrangements up to this many days are ignored; longer "
                    "gaps raise a funding_gap finding in lineage and cohort integrity checks.",
        type="int", default=MIN_GAP_DAYS, min=0, max=90,
    ),
    # --- Email ---
    SettingDef(
        key="email.enabled", group="Email",
        label="Send email notifications",
        description="Institution-wide switch. Off = notifications are still recorded in the "
                    "bell menu but no email leaves the platform. Overrides personal preferences.",
        type="bool", default=True,
    ),
    SettingDef(
        key="email.from_name", group="Email",
        label="Email sender name",
        description="The display name on outgoing email. The actual mailbox/relay (SMTP) is "
                    "infrastructure and stays in the server environment.",
        type="str", default="PGR Platform",
    ),
    # --- Pattern Lab ---
    SettingDef(
        key="pattern_lab.raise_tasks", group="Pattern Lab",
        label="Raise tasks from high predictions",
        description="Off (default): predictions are display-only. On: a batch scoring run "
                    "creates a review task for each student whose predicted probability "
                    "meets the threshold below. Tasks suggest a human look — they never "
                    "change any student record.",
        type="bool", default=False,
    ),
    SettingDef(
        key="pattern_lab.review_interval_days", group="Pattern Lab",
        label="Model review interval (days)",
        description="How long after the latest scoring batch a production model's "
                    "recommended review date falls, absent drift or performance signals "
                    "(which pull the review to today).",
        type="int", default=90, min=30, max=365,
    ),
    SettingDef(
        key="pattern_lab.task_threshold", group="Pattern Lab",
        label="Task-raising probability threshold",
        description="Minimum predicted probability before a review task is raised "
                    "(when task raising is on).",
        type="float", default=0.7, min=0.5, max=0.95,
    ),
    # --- Assistant ---
    SettingDef(
        key="assistant.llm_enabled", group="Assistant",
        label="Allow LLM fallback in Ask PGR",
        description="Off (default): the assistant answers only from its deterministic parser "
                    "and concept graph. On: unrecognised questions may be sent to the "
                    "configured LLM. Requires an API key in the server environment either way.",
        type="bool", default=False,
    ),
]}


def grouped() -> list[dict]:
    """Registry as the API/UI shape, grouped and ordered as defined."""
    groups: dict[str, list[SettingDef]] = {}
    for s in SETTINGS.values():
        groups.setdefault(s.group, []).append(s)
    return [{"group": g, "settings": [
        {"key": s.key, "label": s.label, "description": s.description,
         "type": s.type, "default": s.default, "min": s.min, "max": s.max}
        for s in defs
    ]} for g, defs in groups.items()]
