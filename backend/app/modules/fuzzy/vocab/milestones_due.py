"""Progression milestones due soon."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="milestones_due",
    group="progression",
    description="Progression milestones due in the window (upgrades, annual reviews, submissions).",
    core_tokens=frozenset({"milestone", "milestones", "upgrade", "upgrades", "review", "reviews"}),
    adjacent_tokens=frozenset({
        "due", "upcoming", "next", "coming", "progression", "annual", "quarterly",
    }),
    negative_tokens=frozenset({"overdue", "late", "missed"}),
    examples=(
        "milestones due",
        "upcoming annual reviews",
        "which upgrades are next",
        "progression milestones coming up",
        "reviews due this month",
        "next milestones",
        "annual reviews soon",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="milestone_queue",
    default_args={"filter": "milestones_due"},
)
