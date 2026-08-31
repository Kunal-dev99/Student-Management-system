"""Navigation intent — "take me to X"."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="navigate",
    group="meta",
    description="Jump to a named screen (finance integrity, workforce, students, ...).",
    core_tokens=frozenset({"open", "goto", "go", "jump", "navigate", "take"}),
    adjacent_tokens=frozenset({
        "page", "screen", "view", "to", "me",
        # target hints — one of these must combine with a verb
        "students", "student", "supervision", "workforce", "funding", "finance",
        "recruitment", "admissions", "progression", "portal", "tasks", "settings",
        "integrity", "analytics", "dashboard",
    }),
    negative_tokens=frozenset(),
    examples=(
        "go to funding",
        "open the workforce page",
        "take me to the students screen",
        "jump to funding integrity",
        "navigate to recruitment",
        "open supervision workforce",
        "go to settings",
    ),
    optional_slots=frozenset(),
    tool="navigate",
    card="nav_target",
    default_args={},
)
