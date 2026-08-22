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


class MeetingFormat(str, enum.Enum):
    in_person = "in_person"
    online = "online"
    hybrid = "hybrid"


# Phase 4B.5 — supervisory capacity. A supervisor may hold at most this many current
# supervisees before the platform warns/blocks further primary assignments.
MAX_SUPERVISEES_DEFAULT = 8

# Institutions typically expect a formal supervision meeting at least this often.
EXPECTED_MEETING_INTERVAL_DAYS = 90
