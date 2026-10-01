"""Date rules for facts that can have several periods at once (effective dating, Phase 4).

Funding arrangements and supervisor relationships aren't single-valued — a student can be co-funded
or co-supervised — so they don't use the one-value-at-a-time history engine. They still store
half-open periods (``valid_to`` is the first day no longer true) and follow these rules:

- a change, end or assignment may be back-dated, but not yet future-dated: other features still
  read their ``status`` rather than their dates, so a future date would be wrong until the day;
- a period can't end before it started;
- the same supervisor can't have two overlapping periods for one student.

Recorded time is the row's ``created_at`` / ``updated_at`` plus the audit log.
"""
from __future__ import annotations

from datetime import date

from app.core.errors import WorkflowError
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
