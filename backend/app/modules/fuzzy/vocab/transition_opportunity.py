"""Write intent — advance an opportunity in its workflow (draft → approved → open → …)."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="transition_opportunity",
    group="recruitment",
    description="Advance an opportunity to its next workflow state.",
    core_tokens=frozenset({
        "approve", "open", "publish", "recruit", "recruiting", "close", "closed",
        "pause", "fill", "filled",
    }),
    adjacent_tokens=frozenset({
        "opportunity", "opportunities", "position", "posting", "advert",
    }),
    negative_tokens=frozenset({"payment", "stipend", "task"}),
    examples=(
        "approve the opportunity",
        "open this opportunity for applications",
        "publish the phd in robotics opportunity",
        "close the position",
        "pause the opportunity",
    ),
    optional_slots=frozenset(),
    tool="__write__",
    card="confirm_transition_opportunity",
    write_action="transition_opportunity",
    write_permission="recruitment.write",
)
