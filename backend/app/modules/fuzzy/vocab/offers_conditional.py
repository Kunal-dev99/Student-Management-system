"""Offers with unmet conditions."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="offers_conditional",
    group="recruitment",
    description="Offers issued but still conditional — visa, fees, references outstanding.",
    core_tokens=frozenset({"offers", "offer", "conditional", "conditions"}),
    adjacent_tokens=frozenset({
        "unmet", "outstanding", "visa", "fee", "fees", "reference", "references",
        "pending", "issued",
    }),
    negative_tokens=frozenset({"declined", "withdrawn", "unconditional"}),
    examples=(
        "conditional offers",
        "offers with unmet conditions",
        "outstanding offer conditions",
        "which offers still have visa pending",
        "conditional offer queue",
        "fee conditions unmet",
        "reference conditions outstanding",
    ),
    optional_slots=frozenset(),
    tool="cohort_query",
    card="offer_conditions",
    default_args={"filter": "offers_conditional"},
)
