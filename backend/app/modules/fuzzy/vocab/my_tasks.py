"""My open tasks — inbox for the signed-in user."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="my_tasks",
    group="meta",
    description="Every open task assigned to me.",
    core_tokens=frozenset({"my", "mine", "inbox", "todo", "todos", "to-do", "tasks", "queue", "assigned"}),
    adjacent_tokens=frozenset({"task", "work", "action", "actions", "waiting"}),
    negative_tokens=frozenset({"her", "his", "their", "student", "supervisor"}),
    examples=(
        "my tasks",
        "what's in my inbox",
        "my todo list",
        "open tasks assigned to me",
        "what do i need to do",
        "my queue",
        "tasks waiting on me",
    ),
    optional_slots=frozenset(),
    tool="list_my_tasks",
    card="task_list",
    default_args={},
)
