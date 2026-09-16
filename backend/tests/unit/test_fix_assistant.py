"""ICR G5 fix assistant — per-field cleaning rules and chained transforms.

Deterministic, no model: same input → same fix, and nothing is ever removed (values are cleaned or
clamped, never blanked). Cleaning is per field (names strict, thesis titles lenient) and fixes chain
onto any existing transform rather than replacing it.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.modules.exports.resolutions import VALID_FIX_TRANSFORMS, detect
from app.modules.exports.statutory import TRANSFORMS, apply_chain


def _mapping(field="SURNAME", allowed=None, transform=None):
    return SimpleNamespace(target_field=field, allowed_values=allowed, transform=transform)


def test_strip_profiles_keep_the_right_characters():
    assert TRANSFORMS["strip_name"]("O'Br!en-Smith2") == "O'Bren-Smith"   # digits/symbols out of a name
    assert TRANSFORMS["strip_title"]("Machine Learning: a study #1") == "Machine Learning: a study 1"  # colon kept, # out
    assert TRANSFORMS["strip_general"]("José  Núñez™") == "José Núñez"     # accents kept, ™ out, spaces squeezed
    assert TRANSFORMS["strip_name"](None) is None                          # never invents a value


def test_clamp_pct_corrects_outliers_without_removing():
    f = TRANSFORMS["clamp_pct"]
    assert f("150") == "100" and f("-20") == "0" and f("60") == "60"
    assert f("") == "" and f("abc") == "abc"       # empty/non-numeric left for a human, not blanked


def test_detect_is_per_field():
    # Name: strict profile → strip_name; a colon in a NAME is disallowed.
    assert detect(_mapping("SURNAME", transform="upper"), "O'Br!en") == {"type": "special_characters", "transform": "strip_name"}
    # Thesis title: lenient → a colon is fine (no issue)…
    assert detect(_mapping("THESIS"), "Machine Learning: a study") is None
    # …but a real symbol in a title still flags, with the title strip.
    assert detect(_mapping("THESIS"), "Study #1 ™") == {"type": "special_characters", "transform": "strip_title"}
    # Clean name → nothing; already-stripped chain → nothing.
    assert detect(_mapping("SURNAME", transform="upper"), "OBRIEN") is None
    assert detect(_mapping("SURNAME", transform="upper|strip_name"), "O'Br!en") is None


def test_detect_outliers_and_ignores_dates_and_codes():
    assert detect(_mapping("STULOAD", transform="int"), "150") == {"type": "outlier_pct", "transform": "clamp_pct"}
    assert detect(_mapping("STULOAD", transform="int"), "60") is None
    assert detect(_mapping("COMDATE", transform="date_compact"), "20260101") is None   # a date, not an outlier
    assert detect(_mapping("MODE", allowed=["01", "02"], transform=None), "03") is None  # coded → coding frame handles it


def test_chained_transforms_apply_in_order():
    assert apply_chain("upper|strip_name", "o'br!en") == "O'BREN"   # upper then strip
    assert apply_chain("strip_name|upper", "o'br!en") == "O'BREN"   # order-independent here
    assert apply_chain("upper", "smith") == "SMITH"                 # a single name still works
    assert apply_chain("bogus|upper", "smith") == "SMITH"           # unknown parts skipped, no crash


def test_valid_fix_transforms_are_real():
    for t in VALID_FIX_TRANSFORMS:
        assert t in TRANSFORMS
