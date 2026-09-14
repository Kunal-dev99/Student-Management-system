"""Provenance enforcement — does every value in a composition come from the data?

Schema validation proves a composition is well *shaped*. It says nothing about whether the
values are real. Left to a prompt instruction alone, a model will happily invent an
entirely plausible dashboard: milestones that were never set, supervisors who do not work
here, funding that does not exist. It validates, it renders, and it is fiction.

So the invariant is enforced here instead. Every data-bearing value in the composition must
appear somewhere in the function results the model was given. Anything else is a violation,
and a composition with violations is never shown — it is sent back for repair, and failing
that, refused.

What is deliberately *not* checked:

* **Titles, labels, column headers, narrative prose and the rationale.** These are the
  model's job — describing and framing the data is the whole point of using one.
* **Small integers.** A count of rows is a legitimate calculation, not an invention.

The asymmetry matters: a false positive blocks a good answer, a false negative shows a
fabricated one. When in doubt this errs towards allowing, and catches the class of error
that actually occurs — invented names, dates, references and amounts.
"""
from __future__ import annotations

import re
from typing import Any

# Values below this length carry too little signal to attribute — "N/A", "3", "—".
_MIN_CHECKED_LENGTH = 3

# Placeholders and structural text a composition may legitimately contain.
_ALLOWED = frozenset({
    "—", "-", "n/a", "na", "none", "null", "unknown", "not set", "not recorded",
    "yes", "no", "true", "false", "total", "other",
})

_PUNCT = re.compile(r"[£$€,%\s]")


def _normalise(value: Any) -> str:
    """Comparable form: lowercase, stripped of currency, separators and whitespace."""
    return _PUNCT.sub("", str(value).strip().lower())


def _corpus(collected: dict[str, Any]) -> set[str]:
    """Every leaf value the model was shown, in comparable form."""
    out: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                # Keys are field names the model can legitimately echo as column headers.
                out.add(_normalise(key))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif node is not None:
            text = _normalise(node)
            if text:
                out.add(text)
                # Full names are frequently split across cells ("Elena" / "Ford"), and
                # dates get reformatted, so index the parts too.
                for part in re.split(r"[\s/\-:T]+", str(node).strip().lower()):
                    if len(part) >= _MIN_CHECKED_LENGTH:
                        out.add(_normalise(part))

    walk(collected)
    return out


def _is_grounded(value: Any, corpus: set[str], *, allow_small_int: bool = True) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text or text.lower() in _ALLOWED:
        return True

    # Bare numbers: counts and simple aggregates are legitimate model arithmetic — but
    # only for free-form spots (a table cell computing len(rows), say). A KPI or gauge
    # headline number is presented AS a real aggregate from the data, so it must actually
    # match one, or a hallucinated total (e.g. "0" next to a chart that sums to 470)
    # sails through unnoticed — that is the failure this flag closes.
    if allow_small_int:
        try:
            number = float(_PUNCT.sub("", text))
            if number.is_integer() and abs(number) <= 10_000:
                return True
        except ValueError:
            pass

    normalised = _normalise(text)
    # The short-string bypass below exists for tokens too small to carry real signal
    # ("a", "OK"). A short numeral is not that — "0" vs "470" is exactly the kind of
    # wrong-headline-number this function exists to catch — so strict values skip it
    # and go straight to the corpus check.
    if len(normalised) < _MIN_CHECKED_LENGTH and allow_small_int:
        return True
    if normalised in corpus:
        return True
    # A composed cell may join fields ("Elena Ford — primary"). Grounded if every
    # substantial part is.
    parts = [p for p in re.split(r"[\s/\-:,;()]+", text.lower()) if len(p) >= _MIN_CHECKED_LENGTH]
    if parts and all(_normalise(p) in corpus for p in parts):
        return True
    return False


def _values_to_check(block: dict) -> list[tuple[str, Any]]:
    """Data-bearing values only — never the model's own framing."""
    kind = block.get("type")
    found: list[tuple[str, Any]] = []

    if kind == "table":
        for row in block.get("rows") or []:
            for cell in row:
                found.append(("table cell", cell))
    elif kind == "kpi_row":
        for item in block.get("items") or []:
            # "kpi value*" (not "kpi value") — a headline figure the model claims IS an
            # aggregate from the data, so it is held to the strict check in violations().
            found.append(("kpi value*", item.get("value")))
    elif kind == "timeline":
        for event in block.get("events") or []:
            found.append(("timeline date", event.get("at")))
            found.append(("timeline label", event.get("label")))
            found.append(("timeline detail", event.get("detail")))
    elif kind == "comparison":
        for column in block.get("columns") or []:
            found.append(("comparison column", column.get("label")))
            for value in (column.get("values") or {}).values():
                found.append(("comparison value", value))
    elif kind == "donut":
        for slice_ in block.get("slices") or []:
            found.append(("donut label", slice_.get("label")))
    elif kind in {"line_chart", "bar_chart", "stacked_bar"}:
        for label in block.get("x") or []:
            found.append(("axis label", label))
    elif kind == "sparkline_grid":
        for item in block.get("items") or []:
            found.append(("sparkline label", item.get("label")))
    elif kind in {"donut", "pie"}:
        # Slice labels are the model's way of describing what the data was grouped by, so
        # they legitimately re-case snake_case field values ("Research council" from
        # "research_council"). The grounding check tolerates that separately.
        pass
    elif kind == "gauge":
        # Same reasoning as kpi_row above — the gauge's needle position is presented as
        # a real measurement, so it is checked strictly rather than rubber-stamped.
        found.append(("gauge value*", block.get("value")))
    elif kind == "tree":
        # Node labels and detail lines get scanned. Edge labels are relationship names,
        # legitimately model-authored, so they are exempt.
        for node in block.get("nodes") or []:
            found.append(("tree node", node.get("label")))
            found.append(("tree node detail", node.get("detail")))
    elif kind == "roadmap":
        for step in block.get("steps") or []:
            found.append(("roadmap date", step.get("at")))
            found.append(("roadmap detail", step.get("detail")))
    elif kind == "heatmap":
        for axis in ("rows", "columns"):
            for label in block.get(axis) or []:
                found.append((f"heatmap {axis[:-1]}", label))

    return [(where, value) for where, value in found if value is not None]


def violations(composition: dict, collected: dict[str, Any]) -> list[str]:
    """Human-readable list of values that appear nowhere in the source data."""
    corpus = _corpus(collected)
    found: list[str] = []

    for index, block in enumerate(composition.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        for where, value in _values_to_check(block):
            strict = where.endswith("*")
            if not _is_grounded(value, corpus, allow_small_int=not strict):
                found.append(
                    f"block {index + 1} ({block.get('type')}) "
                    f"{where.rstrip('*')}: {str(value)[:60]!r}"
                )
                if len(found) >= 12:
                    return found
    return found
