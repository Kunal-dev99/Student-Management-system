"""Workforce lens — institution-wide supervisor capacity."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="supervisor_workforce",
    group="people",
    description="Institution-wide supervisor capacity, availability, and assignment backlog.",
    core_tokens=frozenset({"workforce", "capacity", "workload", "load", "caseload"}),
    adjacent_tokens=frozenset({
        "supervisor", "supervisors", "over", "cap", "sabbatical", "available",
        "unavailable", "headroom", "utilisation",
    }),
    negative_tokens=frozenset(),
    examples=(
        "supervisor workload",
        "who's over capacity",
        "supervisor caseload institution wide",
        "workforce lens",
        "which supervisors are overloaded",
        "capacity of supervisors",
        "who is on sabbatical",
    ),
    optional_slots=frozenset(),
    tool="supervisor_workforce",
    card="workforce_strip",
    default_args={},
)
