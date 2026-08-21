"""Supervision enumerations (arch §8.2, §8.7)."""
from __future__ import annotations

import enum


class SupervisorRole(str, enum.Enum):
    primary = "primary"
    co_supervisor = "co_supervisor"
    additional = "additional"


class SupervisionStatus(str, enum.Enum):
    assigned = "assigned"
    accepted = "accepted"
    active = "active"
    changed = "changed"
    ended = "ended"
