"""Students the platform has flagged at risk."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="at_risk_students",
    group="people",
    description="Students with one or more risk flags (progression, funding, supervision).",
    core_tokens=frozenset({"risk", "risky", "flagged", "concerns", "concerning", "worrying", "worried"}),
    adjacent_tokens=frozenset({
        "student", "students", "cohort", "atrisk", "flag", "flags", "amber", "red",
        "falling", "cracks",
    }),
    negative_tokens=frozenset({"low", "safe", "green"}),
    examples=(
        "who is at risk",
        "at risk students",
        "risky cohort",
        "students flagged red",
        "who's falling through the cracks",
        "amber and red flags",
        "risk flags this term",
    ),
    optional_slots=frozenset({"window"}),
    tool="get_analytics",
    card="risk_cohort_list",
    default_args={},
)
