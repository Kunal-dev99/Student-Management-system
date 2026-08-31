"""Analytics — risk / completion / forecasting overview."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="analytics_overview",
    group="meta",
    description="Institution analytics — risk, completion rate, forecasting.",
    core_tokens=frozenset({"analytics", "kpi", "kpis", "metrics", "performance",
                            "completion", "rate"}),
    adjacent_tokens=frozenset({
        "completion", "rate", "risk", "forecast", "trend", "overview", "dashboard",
    }),
    negative_tokens=frozenset(),
    examples=(
        "show analytics",
        "kpis",
        "completion rate",
        "performance metrics",
        "how are we doing",
        "institution dashboard",
        "risk analytics",
    ),
    optional_slots=frozenset(),
    tool="get_analytics",
    card="analytics_tiles",
    default_args={},
)
