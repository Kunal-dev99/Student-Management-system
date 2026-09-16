"""Rule-based resolution dictionary for statutory data-quality issues (ICR G5 fix assistant).

The point of this module: for a *type* of data problem, there is a *known, deterministic fix*. No
model is involved in deciding or applying a fix, so there is no hallucination — every fix is a
named, pure transform. Fixes clean or massage a value at the RETURN layer (they set a transform on
the field mapping); the master student record is never changed and **nothing is ever removed** —
special characters are stripped, outliers are clamped to the valid range.

This is deliberately a small dictionary to start; new (issue type → fix) pairs are added here as the
research into "what fix for what data" continues.
"""
from __future__ import annotations

import re

# Symbols a statutory text field shouldn't carry (accents/letters/digits/basic punctuation are kept).
_SAFE_TEXT = re.compile(r"[^0-9A-Za-zÀ-ÿ .,'\-/()]")
_DATE_TRANSFORMS = {"date_compact", "date_iso", "year"}

# issue type -> deterministic resolution (a named transform + a human explanation)
RESOLUTIONS: dict[str, dict] = {
    "special_characters": {
        "label": "Strip disallowed characters",
        "description": "This text value carries symbols a statutory field shouldn't (e.g. #, *, ™). "
                       "The fix removes them, keeping letters, digits, spaces and basic punctuation. "
                       "The value is cleaned, never blanked.",
        "transform": "strip_special",
    },
    "outlier_pct": {
        "label": "Clamp to the valid 0–100 range",
        "description": "This percentage / FTE value falls outside 0–100. The fix corrects it to the "
                       "nearest valid bound (0 or 100). The value is massaged, not removed.",
        "transform": "clamp_pct",
    },
}

VALID_FIX_TRANSFORMS = {r["transform"] for r in RESOLUTIONS.values()}


def detect(mapping, text: str | None) -> str | None:
    """Return the resolution type for a produced field value, or None. Purely rule-based.

    `mapping` is the field's ReportFieldMapping (carries `allowed_values` and `transform`); `text`
    is the value the return would output for this field after its current transform.
    """
    if not text:
        return None
    # Coded fields are governed by their coding frame (the validation report), not by cleaning.
    if mapping.allowed_values:
        return None
    cur = mapping.transform
    if cur in _DATE_TRANSFORMS:
        return None
    # Numeric percentage/FTE field (mapped with `int`) whose value is out of 0..100 → outlier.
    if cur == "int":
        try:
            n = float(text)
        except (TypeError, ValueError):
            return None
        if n < 0 or n > 100:
            return "outlier_pct"
        return None
    # Plain text field with a disallowed character (and not already being stripped).
    if cur != "strip_special" and _SAFE_TEXT.search(text):
        return "special_characters"
    return None
