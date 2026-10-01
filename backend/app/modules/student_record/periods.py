"""Date rules for facts that can have several periods at once (effective dating, Phase 4).

Funding arrangements and supervisor relationships aren't single-valued — a student can be co-funded
or co-supervised — so they don't use the one-value-at-a-time history engine. They still store
half-open periods (``valid_to`` is the first day no longer true) and follow these rules:

- a change, end or assignment may be back-dated, but not yet future-dated: other features still
  read their ``status`` rather than their dates, so a future date would be wrong until the day;
- a period can't end before it started;
- the same supervisor can't have two overlapping periods for one student;
- a change reaching a signed-off return needs the returns-amendment permission (Phase 5).

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
# Closed years (Phase 5): a reporting year closes when its return is signed off.
# --------------------------------------------------------------------------------------

# Changing what a signed-off return covered is a statutory data amendment (OfS: only for genuine,
# material errors). Like a closed accounting period it belongs to a small returns / student-data
# team, not to everyone who records day-to-day changes — and it is kept separate from
# student.history.correct, which rewrites recorded history.
AMEND_PERMISSION = "returns.amend"


async def assert_backdate_allowed(session, d: date | None, principal, *, what: str,
                                  end: date | None = None) -> None:
    """Refuse a change whose period ``[d, end)`` reaches a signed-off return, unless the user may
    amend returns. Years without a signed-off return stay open to normal back-dating.

    ``principal`` None means an internal call (scheduler, tests, migrations): no check.
    """
    if d is None or principal is None or principal.has_permission(AMEND_PERMISSION):
        return
    from app.modules.student_record.retrospective import affected, signed_off_returns

    hits = affected(await signed_off_returns(session), d, end, None)
    if hits:
        names = ", ".join(f"{r.name} {r.academic_year}" for r in hits)
        raise PermissionError(
            f"{what} is dated {d.isoformat()}, inside the signed-off {names} return. Changing a "
            f"signed-off year is a data amendment and needs the '{AMEND_PERMISSION}' permission "
            "— ask the student data / returns team."
        )
