"""Phase 5.1c — the concept-graph fallback.

These are phrasings nobody wrote an explicit rule for. The strict parser misses them; spreading
activation should still land on the right filter, flagged as an inference rather than a match.
"""
from __future__ import annotations

import pytest

from app.modules.assistant.intents import parse
from app.modules.assistant.semantics import (
    FUNDING,
    MEETING,
    NEGATION,
    RISK,
    SUPERVISION,
    activate,
    score_rules,
    stem,
)


# --- the mechanics ------------------------------------------------------------------------

@pytest.mark.parametrize("word,expected", [
    ("expiring", "expir"), ("expired", "expir"), ("expires", "expir"),
    ("meetings", "meeting"), ("supervising", "supervis"), ("struggling", "struggl"),
])
def test_stemming_unifies_word_forms(word, expected):
    assert stem(word) == expected


def test_activation_spreads_from_meeting_to_supervision():
    """'nobody has met them' never says 'supervision', but that is what it means here."""
    act = activate("nobody has met them")
    assert act[MEETING] > 0
    assert act[SUPERVISION] > 0      # arrived purely via the graph edge
    assert act[NEGATION] > 0


def test_typos_still_activate():
    act = activate("supervsion")     # missing 'i'
    assert act.get(SUPERVISION, 0) > 0.5


def test_veto_prevents_wrong_filter():
    """'funding expiring' must not also fire the 'no active funding' rule."""
    scored = {c.rule.key: c.score for c in score_rules(activate("funding expiring soon"))}
    assert "fundingExpiringWithinDays" in scored
    assert "noActiveFunding" not in scored


# --- end-to-end phrasings the strict parser does not cover ---------------------------------

def test_nobody_has_seen_them():
    got = parse("which students has nobody seen in 6 months")
    assert got is not None
    assert got.tool == "cohort_query"
    assert got.args.get("noSupervisionMeetingInDays") == 180
    assert got.uncertain is True          # inferred, so flagged


def test_money_running_out():
    got = parse("whose money is running out")
    assert got is not None and got.tool == "cohort_query"
    assert "fundingExpiringWithinDays" in got.args


def test_slipping_behind_on_milestones():
    got = parse("students slipping behind on their milestones")
    assert got is not None and got.tool == "cohort_query"
    assert got.args.get("milestoneOverdue") is True


def test_falling_through_the_cracks_maps_to_risk():
    """The exact phrase I claimed rules could never handle."""
    got = parse("who is falling through the cracks")
    assert got is not None
    assert got.tool == "get_analytics"


def test_typo_still_parses():
    got = parse("students with no supervsion meeting in 90 days")
    assert got is not None and got.tool == "cohort_query"
    assert got.args.get("noSupervisionMeetingInDays") == 90


def test_strict_match_is_not_flagged_uncertain():
    """A phrasing the strict parser knows must stay confident, not fall through to the graph."""
    got = parse("students with no supervision meeting in 90 days")
    assert got.uncertain is False
    assert got.args == {"noSupervisionMeetingInDays": 90}


def test_genuinely_unrelated_text_still_returns_none():
    """Flexibility must not become 'matches everything'."""
    assert parse("please book the seminar room for thursday afternoon") is None
    assert parse("what is the wifi password") is None
