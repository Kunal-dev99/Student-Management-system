"""Rule-based intent parser (Phase 5.1b) — the assistant's PRIMARY path.

Why rules rather than a language model for most traffic:
- **Privacy**: student records are personal data; nothing leaves the server.
- **Cost / latency**: zero tokens, ~1ms, versus pennies and seconds.
- **Determinism**: the same sentence always produces the same query — auditable.
- **Honest failure**: an unparsed sentence says "I didn't understand" and offers suggestions,
  instead of confidently returning the wrong students.

This works because the domain is narrow: a bounded set of filters, a bounded vocabulary, and
entity names that already exist in the database to match against. A language model is only needed
for open paraphrase and multi-hop reasoning, so it stays an optional fallback (off by default).

The parser reports what it understood, so the user can verify the interpretation rather than
trusting it blindly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.assistant.semantics import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    activate,
    score_rules,
)

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

CONTRACTIONS = {
    "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
    "isn't": "is not", "aren't": "are not", "don't": "do not",
    "doesn't": "does not", "didn't": "did not", "won't": "will not",
    "who's": "who is", "what's": "what is", "there's": "there is",
}


def normalise(text: str) -> str:
    t = (text or "").strip().lower()
    for k, v in CONTRACTIONS.items():
        t = t.replace(k, v)
    t = re.sub(r"[?!.,;:]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# Duration extraction — "90 days", "6 months", "a year", "this year"
# ---------------------------------------------------------------------------

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
UNIT_DAYS = {"day": 1, "week": 7, "fortnight": 14, "month": 30, "term": 120, "year": 365}

_NUM = r"(?P<num>\d+|" + "|".join(NUMBER_WORDS) + r")"
_UNIT = r"(?P<unit>day|week|fortnight|month|term|year)s?"
DURATION_RE = re.compile(rf"\b{_NUM}\s+{_UNIT}\b")
# Bare periods that imply a window without a number.
BARE_PERIOD_RE = re.compile(r"\b(this (?:year|term)|next (?:year|term)|the year)\b")


@dataclass
class Duration:
    days: int
    start: int
    end: int
    text: str


def find_durations(text: str) -> list[Duration]:
    out: list[Duration] = []
    for m in DURATION_RE.finditer(text):
        raw = m.group("num")
        n = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 1)
        out.append(Duration(n * UNIT_DAYS[m.group("unit")], m.start(), m.end(), m.group(0)))
    for m in BARE_PERIOD_RE.finditer(text):
        days = 365 if "year" in m.group(1) else 120
        out.append(Duration(days, m.start(), m.end(), m.group(0)))
    return sorted(out, key=lambda d: d.start)


# ---------------------------------------------------------------------------
# Filter vocabulary. Each entry: the phrases that name it, and whether it needs
# a negation word nearby ("no", "without", "have not") to be meaningful.
# ---------------------------------------------------------------------------

NEGATIONS = ("no ", "not ", "without ", "never ", "lacking ", "missing ", "have not ", "has not ", "yet to ")

# Words that already imply "overdue/absent" so no separate negation is required.
IMPLICIT_NEG = ("overdue", "late", "behind", "missed", "outstanding", "neglected", "stale", "lapsed")


@dataclass
class FilterSpec:
    key: str                       # cohort_query argument name
    phrases: tuple[str, ...]       # surface forms that name the concept
    kind: str                      # "duration" | "bool"
    needs_negation: bool = False
    default_days: int | None = None
    label: str = ""


FILTERS: tuple[FilterSpec, ...] = (
    FilterSpec(
        key="noSupervisionMeetingInDays",
        phrases=("supervision meeting", "supervisor meeting", "supervisory meeting",
                 "supervision meetings", "met their supervisor", "met with their supervisor",
                 "seen their supervisor", "supervision record", "supervision contact",
                 "been supervised", "supervision"),
        kind="duration", needs_negation=True, default_days=90,
        label="no supervision meeting",
    ),
    FilterSpec(
        key="fundingExpiringWithinDays",
        phrases=("funding expiring", "funding expires", "funding ending", "funding ends",
                 "funding running out", "funding runs out", "stipend ending", "stipend expiring",
                 "scholarship ending", "funding due to end", "funding finishing"),
        kind="duration", default_days=180,
        label="funding expiring",
    ),
    FilterSpec(
        key="noActiveFunding",
        phrases=("unfunded", "no funding", "without funding", "no active funding",
                 "not funded", "self funded", "no stipend"),
        kind="bool",
        label="no active funding",
    ),
    FilterSpec(
        key="milestoneOverdue",
        phrases=("milestone", "milestones", "progression review", "progression",
                 "review overdue", "annual review"),
        kind="bool", needs_negation=True,
        label="milestone overdue",
    ),
)

STATUS_WORDS = {
    "registered": "registered", "active": "active", "completed": "completed",
    "graduated": "completed", "withdrawn": "withdrawn", "suspended": "suspended",
}

THESIS_WORDS = {
    "submitted": "submitted", "under examination": "under_examination",
    "in corrections": "corrections", "corrections": "corrections", "approved": "approved",
}

# Navigation vocabulary (kept here so both nav and cohort parsing share normalisation).
NAV_WORDS = {
    "dashboard": "dashboard", "analytics": "analytics", "students": "students",
    "student": "students", "people": "persons", "persons": "persons", "person": "persons",
    "recruitment": "recruitment", "admissions": "admissions", "supervision": "supervision",
    "progression": "progression", "funding": "funding", "thesis": "thesis", "theses": "thesis",
    "completion": "completion", "tasks": "tasks", "task": "tasks", "workflows": "workflows",
    "integration": "integration", "audit": "audit", "settings": "settings", "portal": "portal",
}

COHORT_TRIGGERS = ("student", "students", "who", "which", "anyone", "list", "show", "find", "how many")


@dataclass
class ParsedIntent:
    tool: str
    args: dict = field(default_factory=dict)
    understood: str = ""          # plain-English readback so the user can verify
    confidence: float = 1.0
    # True when the concept graph guessed rather than the strict parser matching. The answer is
    # still returned (it is read-only and cheap), but labelled so the user can correct it.
    uncertain: bool = False


def _negated_near(text: str, pos: int, window: int = 45) -> bool:
    """Is there a negation (or an implicitly-negative word) shortly before this phrase?"""
    left = text[max(0, pos - window):pos]
    return any(n in left for n in NEGATIONS) or any(w in left for w in IMPLICIT_NEG)


def _nearest_duration(durations: list[Duration], pos: int) -> Duration | None:
    """Attach the duration that follows this filter phrase most closely.

    Lets one sentence carry two windows: "no supervision meeting in 90 days AND funding
    expiring in 6 months" binds 90d to supervision and 180d to funding.
    """
    after = [d for d in durations if d.start >= pos]
    if after:
        return min(after, key=lambda d: d.start - pos)
    return None


def parse_cohort(text: str) -> ParsedIntent | None:
    """Slot-fill a cohort_query from a sentence, or return None if nothing matched."""
    durations = find_durations(text)
    args: dict = {}
    parts: list[str] = []
    used_duration_ids: set[int] = set()

    for spec in FILTERS:
        hit_pos = -1
        for phrase in spec.phrases:
            p = text.find(phrase)
            if p != -1:
                hit_pos = p
                break
        if hit_pos == -1:
            continue
        if spec.needs_negation and not _negated_near(text, hit_pos):
            continue

        if spec.kind == "bool":
            args[spec.key] = True
            parts.append(spec.label)
        else:
            d = _nearest_duration(durations, hit_pos)
            if d is not None and id(d) not in used_duration_ids:
                used_duration_ids.add(id(d))
                args[spec.key] = d.days
                parts.append(f"{spec.label} in {d.days} days")
            else:
                args[spec.key] = spec.default_days
                parts.append(f"{spec.label} in {spec.default_days} days (default)")

    for word, value in STATUS_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            args["status"] = value
            parts.append(f"status {value}")
            break

    for word, value in THESIS_WORDS.items():
        if f"thesis {word}" in text or (word in text and "thesis" in text):
            args["thesisStatus"] = value
            parts.append(f"thesis {value}")
            break

    m = re.search(r"\bsupervised by ([a-z' -]{2,40})", text)
    if m:
        args["supervisorName"] = m.group(1).strip()
        parts.append(f"supervised by {args['supervisorName']}")

    if not args:
        return None
    # A bare status filter with no cohort trigger word is probably not a cohort question.
    if set(args) == {"status"} and not any(t in text for t in COHORT_TRIGGERS):
        return None

    return ParsedIntent(
        tool="cohort_query", args=args,
        understood=" AND ".join(parts),
        confidence=0.9 if len(parts) > 1 else 0.8,
    )


NAV_RE = re.compile(r"^(?:go to|open|take me to|show me the|show|jump to|navigate to)\s+(?P<t>[a-z ]{2,30})$")
TASKS_RE = re.compile(r"\b(my|open|outstanding)\s+tasks?\b|^tasks?$")
RISK_RE = re.compile(r"\bat[- ]risk\b|\brisk list\b|\bwho is at risk\b|\bstruggling\b")
ANALYTICS_RE = re.compile(r"\b(completion rate|attrition|forecast|analytics|how many completed)\b")
E360_RE = re.compile(r"\b(enterprise 360|360|overview of everything|whole population)\b")
OVERVIEW_RE = re.compile(r"\b(state of|status of|how is|tell me about|overview of|summary of|everything about)\b")


def parse(text: str) -> ParsedIntent | None:
    """Parse a sentence into a tool call, or None when the rules don't cover it."""
    t = normalise(text)
    if not t:
        return None

    # Specific intents win over navigation: "open tasks" should answer with the count and a
    # link, not merely navigate. ("go to tasks" still navigates — it doesn't match TASKS_RE.)
    if TASKS_RE.search(t):
        return ParsedIntent("list_my_tasks", {}, "your open tasks")
    if RISK_RE.search(t):
        return ParsedIntent("get_analytics", {}, "students flagged at risk")
    if E360_RE.search(t):
        return ParsedIntent("get_enterprise_360", {}, "the PGR Enterprise 360 summary")

    m = NAV_RE.match(t)
    if m:
        word = m.group("t").strip()
        target = NAV_WORDS.get(word) or NAV_WORDS.get(word.rstrip("s")) or NAV_WORDS.get(word + "s")
        if target:
            return ParsedIntent("navigate", {"target": target}, f"open {target}")

    if ANALYTICS_RE.search(t):
        return ParsedIntent("get_analytics", {}, "completion and forecast analytics")

    cohort = parse_cohort(t)
    if cohort:
        return cohort

    # "state of Tom Fisher" / "tell me about Priya" -> resolve then summarise.
    m = OVERVIEW_RE.search(t)
    if m:
        name = t[m.end():].strip().strip("'\"")
        if name:
            return ParsedIntent("student_overview_by_name", {"query": name},
                                f"an overview of {name}", confidence=0.7)

    # A short, purely alphabetic phrase is most likely a person's name.
    if re.fullmatch(r"[a-z][a-z' -]{1,40}", t) and len(t.split()) <= 3:
        if not any(w in t for w in NAV_WORDS):
            return ParsedIntent("find_student", {"query": t}, f"a student matching '{t}'",
                                confidence=0.6)

    # Nothing matched exactly — fall back to the concept graph, which degrades gracefully
    # instead of refusing (see semantics.py).
    return parse_semantic(t)


def parse_semantic(text: str) -> ParsedIntent | None:
    """Flexible fallback: spreading activation over the concept graph.

    Handles typos, unusual word order, and phrasings nobody wrote a rule for
    ("nobody has seen them in months", "whose money is running out", "who's slipping behind").
    Returns an intent flagged `uncertain` when it is inferring rather than matching.
    """
    activation = activate(text)
    candidates = score_rules(activation)
    if not candidates:
        return None

    top = candidates[0]
    if top.score < LOW_CONFIDENCE:
        return None

    durations = find_durations(text)
    args: dict = {}
    parts: list[str] = []
    used: set[int] = set()

    # A single strong intent (e.g. "at risk") answers directly rather than filtering a cohort.
    if top.rule.kind == "intent":
        tool = top.rule.key.split(":", 1)[1]
        return ParsedIntent(tool, {}, top.rule.label,
                            confidence=top.score, uncertain=top.score < HIGH_CONFIDENCE)

    for cand in candidates:
        if cand.rule.kind == "intent" or cand.score < LOW_CONFIDENCE:
            continue
        rule = cand.rule
        if rule.kind == "bool":
            args[rule.key] = True
            parts.append(rule.label)
        else:
            free = [d for d in durations if id(d) not in used]
            if free:
                d = free[0]
                used.add(id(d))
                args[rule.key] = d.days
                parts.append(f"{rule.label} in {d.days} days")
            else:
                args[rule.key] = rule.default_days
                parts.append(f"{rule.label} in {rule.default_days} days (default)")

    if not args:
        return None
    for word, value in STATUS_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            args["status"] = value
            parts.append(f"status {value}")
            break

    return ParsedIntent(
        "cohort_query", args, " AND ".join(parts),
        confidence=top.score, uncertain=top.score < HIGH_CONFIDENCE,
    )


# Suggestions offered when nothing parses — honest failure beats a wrong guess.
DID_YOU_MEAN = [
    "students with no supervision meeting in 90 days",
    "students with funding expiring in 6 months",
    "unfunded students",
    "students with an overdue milestone",
    "who is at risk",
    "my tasks",
]
