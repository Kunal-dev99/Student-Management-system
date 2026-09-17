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
    `intensity_change` (ICR G4) is the general form of mode change: it records a dated study
    intensity (1-100% FTE), from which study mode is derived (100 = full-time, else part-time),
    so the return can report a real per-year FTE (HESA STULOAD) and the end date recalculates
    from the actual ratio rather than a fixed part-time factor.
    """
    suspension = "suspension"
    extension = "extension"
    mode_change = "mode_change"
    intensity_change = "intensity_change"
    # A mid-term move to a different programme (e.g. MPhil -> PhD, or PhD -> MSc). The event
    # carries previous/new programme ids and an effective date; approval swaps the student's
    # current programme, cancels undecided milestones, and generates the new programme's schedule
    # from the effective date. Cross-type transfers are allowed with warnings.
    programme_change = "programme_change"


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

# ICR G4 — study intensity (FTE %). Full-time is 100%; a part-time student with no explicit
# intensity recorded is treated as this, derived from the historical part-time factor (100/2 = 50).
FULL_TIME_INTENSITY_PCT = 100
DEFAULT_PART_TIME_INTENSITY_PCT = int(round(100 / PART_TIME_FACTOR))


class StudyMode(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"


# --- ICR G1 — taught (PGT / MSc) vs research programmes ---

class ProgrammeType(str, enum.Enum):
    """What kind of lifecycle a programme runs.

    ``research`` is the historical default and behaves exactly as before (Journey tracker,
    thesis, viva, examination). ``taught`` swaps that for modules -> assessments ->
    dissertation -> award. The column defaults to ``research`` so every existing programme is
    unaffected (additive — see the G1 approach doc).
    """
    research = "research"
    taught = "taught"
