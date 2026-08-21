"""Completion enumerations (arch §8.2, §8.11)."""
from __future__ import annotations

import enum


class CompletionStatus(str, enum.Enum):
    pending = "pending"
    requirements_met = "requirements_met"
    award_confirmed = "award_confirmed"
    graduated = "graduated"
