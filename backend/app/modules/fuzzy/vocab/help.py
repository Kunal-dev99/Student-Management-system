"""Help — 'what can you do'."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="help",
    group="meta",
    description="Show the intent surface — the questions the assistant knows how to answer.",
    core_tokens=frozenset({"help", "capabilities", "commands", "examples", "ask"}),
    adjacent_tokens=frozenset({
        "what", "can", "you", "do", "ask", "assistant",
    }),
    negative_tokens=frozenset(),
    examples=(
        "help",
        "what can you do",
        "what can i ask",
        "capabilities",
        "list commands",
        "give me examples",
        "how do i use this",
    ),
    optional_slots=frozenset(),
    tool="__help__",
    card="help_surface",
    default_args={},
)
