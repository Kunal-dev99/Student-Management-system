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


# --- Phase 6.5 — PGR exception lifecycle (CIO vision GAP-06) ---

class LifecycleEventType(str, enum.Enum):
    """Exceptions that change a research timeline.

    `suspension` pauses the journey (illness, maternity, fieldwork interruption); `extension`
    grants additional time without pausing; `mode_change` moves between full- and part-time.
    """
    suspension = "suspension"
    extension = "extension"
    mode_change = "mode_change"


class LifecycleEventStatus(str, enum.Enum):
    requested = "requested"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


# Statuses a student must be in for a suspension to be requested.
SUSPENDABLE_STATUSES = {StudentStatus.registered, StudentStatus.active}

# While in these statuses a student is paused: no funding-expiry chasing, no milestone
# generation, no overdue escalation (arch §9.3 — do not chase a student who is not studying).
PAUSED_STATUSES = {StudentStatus.suspended, StudentStatus.on_leave}

# Part-time study stretches the expected duration by this factor when the mode changes.
PART_TIME_FACTOR = 2.0


class StudyMode(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
