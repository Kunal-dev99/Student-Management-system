"""Fuzzy time-phrase parser.

Turns period sentinels (from the normaliser) and free numeric phrases like
"last 30 days" / "6 months" into a canonical `TimeSlot` the tools can consume.
Deterministic; no external clock — callers pass `today` for testability.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


# ---- Sentinels emitted by the normaliser ---------------------------------

_SENTINELS = {
    "period_today":        lambda t: (t, t),
    "period_yesterday":    lambda t: (t - timedelta(days=1), t - timedelta(days=1)),
    "period_thisweek":     lambda t: (t - timedelta(days=t.weekday()), t),
    "period_lastweek":     lambda t: (t - timedelta(days=t.weekday() + 7),
                                       t - timedelta(days=t.weekday() + 1)),
    "period_thismonth":    lambda t: (t.replace(day=1), t),
    "period_lastmonth":    lambda t: _prev_month(t),
    "period_nextmonth":    lambda t: _next_month(t),
    "period_thisyear":     lambda t: (t.replace(month=1, day=1), t),
    "period_lastyear":     lambda t: (t.replace(year=t.year - 1, month=1, day=1),
                                       t.replace(year=t.year - 1, month=12, day=31)),
    "period_thisquarter":  lambda t: _quarter(t, offset=0),
    "period_lastquarter":  lambda t: _quarter(t, offset=-1),
    "period_q1":           lambda t: (date(t.year, 1, 1),  date(t.year, 3, 31)),
    "period_q2":           lambda t: (date(t.year, 4, 1),  date(t.year, 6, 30)),
    "period_q3":           lambda t: (date(t.year, 7, 1),  date(t.year, 9, 30)),
    "period_q4":           lambda t: (date(t.year, 10, 1), date(t.year, 12, 31)),
}


# ---- Free numeric periods ------------------------------------------------
#
# "last 30 days", "over the past 6 months", "in 90 days", "next 2 weeks".

_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "quarter": 91, "year": 365}
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}

_LAST_RE = re.compile(
    rf"\b(?:last|past|previous|over the (?:last|past))\s+(\d+|{'|'.join(_NUM_WORDS)})\s+(day|week|month|quarter|year)s?\b"
)
_NEXT_RE = re.compile(
    rf"\b(?:next|coming|upcoming|in the next|within(?: the next)?)\s+(\d+|{'|'.join(_NUM_WORDS)})\s+(day|week|month|quarter|year)s?\b"
)
_IN_RE = re.compile(
    rf"\bin\s+(\d+|{'|'.join(_NUM_WORDS)})\s+(day|week|month|quarter|year)s?\b"
)


@dataclass(frozen=True)
class TimeSlot:
    start: date
    end: date
    phrase: str

    def as_iso(self) -> dict[str, str]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat()}


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else _NUM_WORDS.get(token, 1)


def _prev_month(t: date) -> tuple[date, date]:
    first_this = t.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, last_prev


def _next_month(t: date) -> tuple[date, date]:
    # First of next month.
    if t.month == 12:
        first = date(t.year + 1, 1, 1)
    else:
        first = date(t.year, t.month + 1, 1)
    # Last of next month = day before the following month's first.
    if first.month == 12:
        end = date(first.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(first.year, first.month + 1, 1) - timedelta(days=1)
    return first, end


def _quarter(t: date, offset: int) -> tuple[date, date]:
    q = (t.month - 1) // 3 + offset
    year = t.year + (q // 4)
    q_idx = q % 4
    start_month = q_idx * 3 + 1
    start = date(year, start_month, 1)
    end_month = start_month + 2
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, end_month + 1, 1) - timedelta(days=1)
    return start, end


def parse_time(text: str, *, today: date) -> TimeSlot | None:
    """Best-effort single-slot extraction. First sentinel wins; else first numeric phrase."""
    tokens = text.split()
    for tok in tokens:
        if tok in _SENTINELS:
            start, end = _SENTINELS[tok](today)
            return TimeSlot(start=start, end=end, phrase=tok)

    m = _LAST_RE.search(text)
    if m:
        n = _to_int(m.group(1))
        days = n * _UNIT_DAYS[m.group(2)]
        return TimeSlot(start=today - timedelta(days=days), end=today, phrase=m.group(0))

    m = _NEXT_RE.search(text) or _IN_RE.search(text)
    if m:
        n = _to_int(m.group(1))
        days = n * _UNIT_DAYS[m.group(2)]
        return TimeSlot(start=today, end=today + timedelta(days=days), phrase=m.group(0))

    return None
