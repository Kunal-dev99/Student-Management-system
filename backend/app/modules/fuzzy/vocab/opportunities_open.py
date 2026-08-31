"""Open recruitment opportunities."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="opportunities_open",
    group="recruitment",
    description="Recruitment opportunities currently open for applications.",
    core_tokens=frozenset({"opportunities", "opportunity", "postings", "posting", "vacancies", "vacancy"}),
    adjacent_tokens=frozenset({
        "open", "live", "available", "recruiting", "current", "advertised",
    }),
    negative_tokens=frozenset({"closed", "paused", "filled"}),
    examples=(
        "open opportunities",
        "live postings",
        "current vacancies",
        "which posts are recruiting",
        "opportunities available now",
        "advertised opportunities",
        "what opportunities are live",
    ),
    optional_slots=frozenset(),
    tool="cohort_query",
    card="opportunity_list",
    default_args={"filter": "opportunities_open"},
)
