"""Supervision meetings overdue — students not seen recently enough."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="supervision_meetings_overdue",
    group="progression",
    description="Students whose supervisor meetings are past due.",
    core_tokens=frozenset({"meeting", "meetings", "seen", "supervised"}),
    adjacent_tokens=frozenset({
        "overdue", "late", "no", "without", "haven", "not", "recent",
        "supervision", "supervisor",
    }),
    negative_tokens=frozenset({"payment", "stipend"}),
    examples=(
        "students with no meeting in 90 days",
        "supervision meetings overdue",
        "who hasn't been seen recently",
        "students without a recent supervision meeting",
        "overdue supervisions",
        "meetings not held in the last term",
        "supervision gaps",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="supervision_gap_list",
    default_args={"filter": "meetings_overdue"},
)
