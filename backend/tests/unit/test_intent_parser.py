"""Phase 5.1b — the rule-based intent parser.

These are the questions the assistant must answer without a model. Pure functions, no DB, no
network — so the whole suite runs in milliseconds.
"""
from __future__ import annotations

import pytest

from app.modules.assistant.intents import find_durations, normalise, parse


# --- normalisation / duration extraction -------------------------------------------------

@pytest.mark.parametrize(
    "text,expected_days",
    [
        ("90 days", 90),
        ("6 months", 180),
        ("a year", 365),
        ("two weeks", 14),
        ("12 months", 360),
        ("this year", 365),
    ],
)
def test_duration_extraction(text, expected_days):
    found = find_durations(normalise(text))
    assert found and found[0].days == expected_days


def test_contractions_are_expanded():
    assert "have not" in normalise("students who haven't been supervised")


# --- cohort slot filling ------------------------------------------------------------------

def test_supervision_gap_with_explicit_window():
    got = parse("Which students have no supervision meeting in 90 days?")
    assert got.tool == "cohort_query"
    assert got.args == {"noSupervisionMeetingInDays": 90}
    assert "no supervision meeting in 90 days" in got.understood


def test_supervision_gap_uses_default_window_when_unstated():
    got = parse("students without a supervision meeting")
    assert got.args["noSupervisionMeetingInDays"] == 90
    assert "default" in got.understood


def test_negation_is_required_for_supervision_filter():
    # Mentioning supervision positively is NOT a request for the gap filter.
    assert parse("supervision") is None or parse("supervision").tool != "cohort_query"


def test_implicit_negation_words_count():
    got = parse("students with overdue supervision")
    assert got.tool == "cohort_query"
    assert "noSupervisionMeetingInDays" in got.args


def test_two_filters_bind_their_own_windows():
    """The hard case: two conditions, two durations, each bound to the right filter."""
    got = parse(
        "students with no supervision meeting in 90 days and funding expiring in 6 months"
    )
    assert got.tool == "cohort_query"
    assert got.args["noSupervisionMeetingInDays"] == 90
    assert got.args["fundingExpiringWithinDays"] == 180
    assert got.understood.count("AND") == 1


def test_unfunded_is_a_boolean_filter():
    got = parse("show me unfunded students")
    assert got.args == {"noActiveFunding": True}


def test_milestone_overdue():
    got = parse("which students have an overdue milestone")
    assert got.args.get("milestoneOverdue") is True


def test_status_filter():
    got = parse("list withdrawn students")
    assert got.args.get("status") == "withdrawn"


def test_supervised_by_name():
    got = parse("students supervised by elena ford")
    assert got.args.get("supervisorName") == "elena ford"


# --- other intents ------------------------------------------------------------------------

@pytest.mark.parametrize("text,target", [
    ("go to funding", "funding"),
    ("open thesis", "thesis"),
    ("take me to analytics", "analytics"),
    ("show me the dashboard", "dashboard"),
])
def test_navigation(text, target):
    got = parse(text)
    assert got.tool == "navigate" and got.args["target"] == target


@pytest.mark.parametrize("text", ["my tasks", "tasks", "open tasks"])
def test_tasks_intent(text):
    assert parse(text).tool == "list_my_tasks"


@pytest.mark.parametrize("text", ["who is at risk", "at-risk students", "the risk list"])
def test_risk_intent(text):
    assert parse(text).tool == "get_analytics"


def test_overview_by_name():
    got = parse("what's the state of Tom Fisher")
    assert got.tool == "student_overview_by_name"
    assert got.args["query"] == "tom fisher"


def test_bare_name_is_treated_as_a_lookup():
    got = parse("Marcus Bell")
    assert got.tool == "find_student" and got.args["query"] == "marcus bell"


def test_unparseable_returns_none_rather_than_guessing():
    """The safety property: unknown phrasing must NOT silently become a wrong query."""
    assert parse("explain the reasoning behind our last strategy away day") is None
    assert parse("") is None


def test_open_analytical_question_never_invents_a_cohort_filter():
    """A keyword may map to a safe dashboard answer, but must never fabricate a student filter.

    Returning the analytics summary for a question mentioning attrition is honest; returning a
    *wrong list of students* would not be.
    """
    got = parse("is funding the underlying driver of our attrition problem this decade")
    assert got is None or got.tool != "cohort_query"
