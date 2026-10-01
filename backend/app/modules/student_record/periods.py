"""Date rules for facts that can have several periods at once (effective dating, Phase 4).

Funding arrangements and supervisor relationships aren't single-valued — a student can be co-funded
or co-supervised — so they don't use the one-value-at-a-time history engine. They still store
half-open periods (``valid_to`` is the first day no longer true) and follow these rules:

- a change, end or assignment may be back-dated, but not yet future-dated: other features still
  read their ``status`` rather than their dates, so a future date would be wrong until the day;
- a period can't end before it started;
- the same supervisor can't have two overlapping periods for one student;
- dates before the open reporting year need the history-correction permission (Phase 5).

Recorded time is the row's ``created_at`` / ``updated_at`` plus the audit log.
"""
from __future__ import annotations

from datetime import date

from app.core.errors import PermissionError, WorkflowError  # noqa: A004
from app.modules.student_record import fact_history


def effective_date(d: date | None, *, what: str) -> date:
    """The date a change takes effect: today by default; back-dating allowed, future not yet."""
    today = fact_history.today()
    if d is None:
        return today
    if d > today:
        raise WorkflowError(
            f"{what} can't be dated in the future yet — record it on the day it takes effect "
            "(back-dating is fine)"
        )
    return d


def assert_not_before_start(start: date, end: date, *, what: str) -> None:
    if end < start:
        raise WorkflowError(f"{what} can't take effect before the period started ({start})")


def overlaps(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    """Do two half-open periods overlap? ``None`` = open-ended."""
    return (a_to is None or a_to > b_from) and (b_to is None or b_to > a_from)


# --------------------------------------------------------------------------------------
# Back-dating limit (Phase 5): free within the open reporting year, elevated permission before it.
# --------------------------------------------------------------------------------------

# Back-dating into a closed reporting year rewrites what an earlier return said, so it needs the
# same permission as correcting history.
BACKDATE_PERMISSION = "student.history.correct"


def open_year_start(on: date | None = None) -> date:
    """1 August of the HESA reporting year that contains ``on`` (default today)."""
    on = on or fact_history.today()
    return date(on.year if on.month >= 8 else on.year - 1, 8, 1)


def assert_backdate_allowed(d: date | None, principal, *, what: str) -> None:
    """Refuse a date before the open reporting year unless the user may correct history.

    ``principal`` None means an internal call (scheduler, tests, migrations): no check.
    """
    if d is None or principal is None:
        return
    start = open_year_start()
    if d < start and not principal.has_permission(BACKDATE_PERMISSION):
        raise PermissionError(
            f"{what} is dated {d.isoformat()}, before the open reporting year (from "
            f"{start.isoformat()}). Back-dating into a closed year needs the "
            f"'{BACKDATE_PERMISSION}' permission — ask Registry."
        )
