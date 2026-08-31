"""Supervisor sabbaticals colliding with supervisee milestones."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="sabbatical_conflicts",
    group="people",
    description="Supervisors on sabbatical while a supervisee has a milestone or viva in the window.",
    core_tokens=frozenset({"sabbatical", "sabbaticals", "leave"}),
    adjacent_tokens=frozenset({
        "conflict", "conflicts", "clash", "clashes", "supervisor", "supervisors",
        "colliding", "overlap",
    }),
    negative_tokens=frozenset(),
    examples=(
        "sabbatical conflicts",
        "supervisors on leave with vivas coming up",
        "sabbatical clashes with milestones",
        "who's on sabbatical when their student needs them",
        "supervisor leave overlap",
        "sabbatical conflict list",
        "colliding sabbaticals",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="sabbatical_conflict",
    default_args={"filter": "sabbatical_conflicts"},
)
