"""HESA sign-offs pending — the statutory make-real gate."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="pending_signoffs",
    group="progression",
    description="Statutory sign-offs still open — records not locked.",
    core_tokens=frozenset({"signoff", "signoffs", "sign", "signed", "sign-off"}),
    adjacent_tokens=frozenset({
        "hesa", "statutory", "pending", "open", "outstanding", "unsigned",
        "record", "records", "profile", "profiles",
    }),
    negative_tokens=frozenset({"complete", "done", "closed"}),
    examples=(
        "pending sign-offs",
        "hesa signoffs outstanding",
        "who hasn't been signed off",
        "unsigned statutory records",
        "signoffs open",
        "which records still need signing",
        "statutory sign off queue",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="signoff_queue",
    default_args={"filter": "pending_signoffs"},
)
