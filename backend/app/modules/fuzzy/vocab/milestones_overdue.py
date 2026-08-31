"""Progression milestones that are past due — negative twin of milestones_due."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="milestones_overdue",
    group="progression",
    description="Progression milestones past their due date and not yet completed.",
    core_tokens=frozenset({"overdue", "late", "missed"}),
    adjacent_tokens=frozenset({
        "milestone", "milestones", "upgrade", "upgrades", "review", "reviews",
        "progression", "annual",
    }),
    negative_tokens=frozenset({"payment", "stipend", "meeting"}),
    examples=(
        "overdue milestones",
        "missed progression reviews",
        "late upgrades",
        "which milestones are behind",
        "progression that's overdue",
        "students who missed their annual review",
        "overdue upgrade panels",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="milestone_overdue",
    default_args={"filter": "milestones_overdue"},
)
