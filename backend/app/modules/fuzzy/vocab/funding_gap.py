"""Students whose funding chain is broken or ending soon."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="funding_gap",
    group="finance",
    description="Students with a funding gap — expiring, missing, or lapsed arrangement.",
    core_tokens=frozenset({"gap", "gaps", "expiring", "expired", "lapsed", "missing"}),
    adjacent_tokens=frozenset({
        "funding", "arrangement", "arrangements", "stipend", "cover", "coverage",
    }),
    negative_tokens=frozenset({"held", "overdue", "reference"}),
    examples=(
        "funding gaps",
        "students with expiring funding",
        "funding arrangement about to lapse",
        "who has a funding gap",
        "missing funding coverage",
        "expired funding",
        "students whose funding ends soon",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="funding_gap_list",
    default_args={"filter": "funding_gap"},
)
