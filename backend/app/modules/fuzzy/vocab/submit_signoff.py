"""Write intent — submit a statutory sign-off for a student."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="submit_signoff",
    group="progression",
    description="Sign off a student's statutory record (HESA-ready lock).",
    core_tokens=frozenset({"signoff", "sign-off", "sign"}),
    adjacent_tokens=frozenset({
        "statutory", "record", "hesa", "submit", "lock",
    }),
    negative_tokens=frozenset({"pending", "outstanding", "unsigned"}),
    examples=(
        "sign off this student",
        "submit sign-off for alice",
        "sign off alice's statutory record",
        "lock the statutory record",
        "signoff for hesa",
    ),
    optional_slots=frozenset({"person"}),
    tool="__write__",
    card="confirm_submit_signoff",
    write_action="submit_signoff",
    write_permission="student.write",
)
