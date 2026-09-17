"""Human-facing catalog for the transforms an admin can pick in the mapping form.

The transform NAMES (``strip_name``, ``hesa_yn``, …) are what the return actually stores and
runs at Generate time. This module gives them plain-English labels and one-line descriptions so
the picker doesn't ask the admin to read code.

Kept next to the transform functions so a new transform in ``statutory.TRANSFORMS`` without a
corresponding entry here fails the pin test in ``tests/unit/test_transforms_catalog.py``.
"""
from __future__ import annotations


CATEGORIES = ("Format", "Coding frame", "Cleaning", "Number")

CATALOG: list[dict] = [
    # -------- Format --------
    {"name": "upper", "category": "Format", "label": "Uppercase",
     "description": "Uppercase the text ('rossi' → 'ROSSI')."},
    {"name": "lower", "category": "Format", "label": "Lowercase",
     "description": "Lowercase the text ('Rossi' → 'rossi')."},
    {"name": "str", "category": "Format", "label": "Cast to text",
     "description": "Convert whatever value is there to a plain string."},
    {"name": "int", "category": "Number", "label": "Cast to integer",
     "description": "Convert to a whole number (drops any decimals)."},
    {"name": "date_iso", "category": "Format", "label": "Date · YYYY-MM-DD",
     "description": "Format a date as ISO 8601 (e.g. 2026-09-17)."},
    {"name": "date_compact", "category": "Format", "label": "Date · YYYYMMDD (HESA)",
     "description": "Format a date as the compact HESA form (e.g. 20260917)."},
    {"name": "year", "category": "Format", "label": "Year only",
     "description": "Extract just the 4-digit year from a date."},
    {"name": "bool_yn", "category": "Format", "label": "Boolean · Y / N",
     "description": "Render True as 'Y' and False as 'N' (HESA convention)."},

    # -------- HESA coding frames (map a raw value to a HESA code) --------
    {"name": "hesa_sex", "category": "Coding frame", "label": "HESA · SEXID coding",
     "description": "Map 'female / male / other / not specified' to HESA codes 10 / 11 / 12 / 13."},
    {"name": "hesa_mode", "category": "Coding frame", "label": "HESA · MODE coding",
     "description": "Map 'full_time / part_time / sandwich / writing_up' to HESA MODE codes."},
    {"name": "hesa_yn", "category": "Coding frame", "label": "HESA · Y/N flag",
     "description": "Map booleans, yes/no, 1/0 to the HESA 'Y' / 'N' one-letter code."},
    {"name": "hesa_studylevel", "category": "Coding frame", "label": "HESA · STUDYLEVEL coding",
     "description": "Map 'phd / mphil / masters / pgdip' to HESA STUDYLEVEL codes (D00, M11, H11, I11)."},
    {"name": "hesa_route", "category": "Coding frame", "label": "HESA · ENTRYROUTE coding",
     "description": "Map 'opportunity / proposal' to HESA ENTRYROUTE values."},

    # -------- Cleaning (data quality fixes; can be chained onto anything) --------
    {"name": "strip_name", "category": "Cleaning", "label": "Clean · name-safe characters",
     "description": "Keep only letters, apostrophes, hyphens and single spaces. For SURNAME / FNAMES."},
    {"name": "strip_title", "category": "Cleaning", "label": "Clean · title-safe characters",
     "description": "Keep letters, digits, punctuation (colons, commas), spaces. For thesis titles."},
    {"name": "strip_general", "category": "Cleaning", "label": "Clean · general text",
     "description": "Strip disallowed symbols, keep letters / digits / basic punctuation. Default."},
    {"name": "strip_special", "category": "Cleaning", "label": "Clean · strip specials (legacy alias)",
     "description": "Back-compat alias of 'Clean · general text' — use that instead."},
    {"name": "clamp_pct", "category": "Number", "label": "Clamp to 0–100",
     "description": "Force a percentage value into the 0–100 range."},
]


def as_dict() -> dict:
    """Serialise the catalog for the API — grouped by category so the picker can render sections."""
    grouped: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for t in CATALOG:
        cat = t["category"] if t["category"] in grouped else "Format"
        grouped.setdefault(cat, []).append(t)
    return {
        "categories": [
            {"category": cat, "transforms": grouped[cat]}
            for cat in CATEGORIES if grouped.get(cat)
        ],
        # Flat list for callers that just need names (validation, tests).
        "names": [t["name"] for t in CATALOG],
    }


def known_names() -> set[str]:
    return {t["name"] for t in CATALOG}
