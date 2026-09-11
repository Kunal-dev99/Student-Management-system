"""Cohort intent — students with no currently-active funding arrangement."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="unfunded_students",
    group="finance",
    description="Students with no currently-active funding arrangement.",
    core_tokens=frozenset({"unfunded", "self", "self-funded", "no", "without"}),
    adjacent_tokens=frozenset({
        "students", "student", "funding", "funded", "active",
        "stipend", "scholarship",
    }),
    negative_tokens=frozenset({"expiring", "ending", "overdue"}),
    examples=(
        "unfunded students",
        "students with no active funding",
        "self funded students",
        "students without a stipend",
    ),
    optional_slots=frozenset(),
    tool="cohort_query",
    card="cohort_list",
    default_args={"noActiveFunding": True},
    write_action=None,
    write_permission=None,
)
