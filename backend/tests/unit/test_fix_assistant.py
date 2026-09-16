"""ICR G5 fix assistant — the rule-based cleaning transforms and the issue detector.

Deterministic, no model: same input → same fix, and nothing is ever removed (values are cleaned or
clamped, never blanked).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.modules.exports.resolutions import RESOLUTIONS, detect
from app.modules.exports.statutory import TRANSFORMS


def _mapping(allowed=None, transform=None):
    return SimpleNamespace(allowed_values=allowed, transform=transform)


def test_strip_special_keeps_letters_removes_symbols():
    f = TRANSFORMS["strip_special"]
    assert f("O'Brien-Smith") == "O'Brien-Smith"          # apostrophe + hyphen kept
    assert f("Sm!th#*") == "Smth"                          # symbols removed
    assert f("José  Núñez™") == "José Núñez"               # accents kept, ™ removed, spaces squeezed
    assert f(None) is None                                  # never invents a value


def test_clamp_pct_corrects_outliers_without_removing():
    f = TRANSFORMS["clamp_pct"]
    assert f("150") == "100"      # above range → upper bound
    assert f("-20") == "0"        # below range → lower bound
    assert f("60") == "60"        # in range → unchanged
    assert f("") == ""            # empty stays empty (not removed)
    assert f("abc") == "abc"      # non-numeric left for a human, not blanked


def test_detect_flags_special_characters_on_text_fields():
    assert detect(_mapping(transform=None), "Sm!th") == "special_characters"
    assert detect(_mapping(transform="upper"), "O'BRIEN") is None          # clean text → no issue
    assert detect(_mapping(transform="strip_special"), "Sm!th") is None    # already being stripped


def test_detect_flags_pct_outliers_and_ignores_dates_and_codes():
    assert detect(_mapping(transform="int"), "150") == "outlier_pct"
    assert detect(_mapping(transform="int"), "60") is None                 # in range
    assert detect(_mapping(transform="date_compact"), "20260101") is None  # a date, not an outlier
    assert detect(_mapping(allowed=["01", "02"], transform=None), "03") is None  # coded → coding-frame handles it


def test_every_resolution_names_a_real_transform():
    for r in RESOLUTIONS.values():
        assert r["transform"] in TRANSFORMS
