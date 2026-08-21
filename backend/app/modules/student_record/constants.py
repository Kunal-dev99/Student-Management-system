"""Student record enumerations (arch §8.2)."""
from __future__ import annotations

import enum


class StudentStatus(str, enum.Enum):
    prospective = "prospective"
    registered = "registered"
    active = "active"
    on_leave = "on_leave"
    suspended = "suspended"
    completed = "completed"
    withdrawn = "withdrawn"
    terminated = "terminated"


class StudyMode(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
