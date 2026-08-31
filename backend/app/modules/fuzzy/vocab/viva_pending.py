"""Vivas pending — awaiting examiner appointment or actual viva."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="viva_pending",
    group="progression",
    description="Students in the viva pipeline — awaiting appointment or viva itself.",
    core_tokens=frozenset({"viva", "vivas"}),
    adjacent_tokens=frozenset({
        "pending", "upcoming", "scheduled", "next", "examiner", "examiners",
        "defence", "defense",
    }),
    negative_tokens=frozenset(),
    examples=(
        "vivas pending",
        "upcoming vivas",
        "scheduled vivas",
        "who has a viva coming up",
        "students awaiting viva",
        "next viva defence",
        "examiners awaiting appointment",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="viva_queue",
    default_args={"filter": "viva_pending"},
)
