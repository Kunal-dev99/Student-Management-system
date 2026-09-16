"""Rule-based resolution dictionary for statutory data-quality issues (ICR G5 fix assistant).

The point of this module: for a *type* of data problem there is a *known, deterministic fix*. No
model is involved in deciding or applying a fix, so there is no hallucination — every fix is a
named, pure transform. Fixes clean or massage a value at the RETURN layer (they append a transform
to the field mapping); the master student record is never changed and **nothing is ever removed**.

Cleaning is **per field**: a name is filtered strictly (letters/space/apostrophe/hyphen), a thesis
title leniently (keeps digits, colons and richer punctuation), everything else by a general rule.
Extend ``FIELD_RULES`` as the research into "what fix for what data" continues.
"""
from __future__ import annotations

import re

# Disallowed-character class per text profile — mirrors STRIP_PROFILES in statutory.py so a detected
# issue maps to the matching strip transform (strip_<profile>).
_PROFILE_DISALLOWED = {
    "name": re.compile(r"[^A-Za-zÀ-ÿ '\-]"),
    "title": re.compile(r"[^0-9A-Za-zÀ-ÿ '\-.,:;/&()]"),
    "general": re.compile(r"[^0-9A-Za-zÀ-ÿ .,'\-/()]"),
}
_DATE_TRANSFORMS = {"date_compact", "date_iso", "year"}

# Per-field cleaning rules. `text` picks the character profile; `outlier` gives a numeric range.
# A field not listed here defaults to the "general" text profile (and no outlier check).
FIELD_RULES: dict[str, dict] = {
    "SURNAME": {"text": "name"},
    "FNAMES": {"text": "name"},
    "THESIS": {"text": "title"},
    "COURSEID": {"text": "general"},
    "STULOAD": {"outlier": (0, 100)},   # FTE / study-load percentage
}

# issue type -> human-facing label + explanation (the transform is chosen per field below).
RESOLUTIONS: dict[str, dict] = {
    "special_characters": {
        "label": "Strip disallowed characters",
        "description": "This text value carries characters this field shouldn't. The fix removes "
                       "them using the field's own rule (names are strict; thesis titles keep "
                       "colons and punctuation). The value is cleaned, never blanked.",
    },
    "outlier_pct": {
        "label": "Clamp to the valid 0–100 range",
        "description": "This percentage / FTE value falls outside 0–100. The fix corrects it to the "
                       "nearest valid bound. The value is massaged, not removed.",
    },
}

# Fix transforms the apply endpoint will accept (the strip_<profile> family + the clamp).
VALID_FIX_TRANSFORMS = {"strip_name", "strip_title", "strip_general", "strip_special", "clamp_pct"}


def detect(mapping, text: str | None) -> dict | None:
    """Return ``{"type", "transform"}`` for a produced field value, or None. Purely rule-based and
    per-field: the chosen strip transform matches the field's text profile.
    """
    if not text:
        return None
    if mapping.allowed_values:               # coded fields are handled by their coding frame
        return None
    chain = {t.strip() for t in (mapping.transform or "").split("|") if t.strip()}
    if chain & _DATE_TRANSFORMS:
        return None

    rule = FIELD_RULES.get(mapping.target_field, {})

    # Numeric outlier (a percentage/FTE-style field mapped with `int`, or an explicit range rule).
    if "int" in chain or "outlier" in rule:
        lo, hi = rule.get("outlier", (0, 100))
        try:
            n = float(text)
        except (TypeError, ValueError):
            n = None
        if n is not None and (n < lo or n > hi) and "clamp_pct" not in chain:
            return {"type": "outlier_pct", "transform": "clamp_pct"}
        # a numeric field that's in range has nothing else to clean
        if "int" in chain:
            return None

    # Special characters — per the field's text profile.
    profile = rule.get("text", "general")
    strip_transform = f"strip_{profile}"
    if strip_transform not in chain and _PROFILE_DISALLOWED[profile].search(text):
        return {"type": "special_characters", "transform": strip_transform}
    return None
