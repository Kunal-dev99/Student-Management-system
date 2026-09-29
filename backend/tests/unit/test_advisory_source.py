"""Assisted-ingest source handling: bot-wall detection + structure-preserving extraction.

HESA's coding manual is bot-protected, so a server fetch returns a Cloudflare interstitial, not the
document. We must refuse that (never feed it to the AI), and when we DO have real HESA HTML we must
keep its table/list structure so a "valid entries" table reads as one code per line.
"""
from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.modules.exports.advisory_source import extract_text, looks_bot_blocked


def test_cloudflare_interstitial_is_detected_and_refused():
    wall = (
        b"<html><head><title>Just a moment...</title></head>"
        b"<body>Performing security verification</body></html>"
    )
    assert looks_bot_blocked(
        "Just a moment... performing security verification"
    )
    with pytest.raises(ValidationAppError) as exc:
        extract_text(wall, content_type="text/html")
    assert "upload" in str(exc.value).lower()   # actionable: tells the user what to do


def test_hesa_field_table_extracts_one_code_per_line():
    html = (
        b"<html><body><h1>SEXID</h1><p>Sex identifier</p>"
        b"<table><tr><td>10</td><td>Female</td></tr>"
        b"<tr><td>11</td><td>Male</td></tr>"
        b"<tr><td>96</td><td>Information refused</td></tr></table></body></html>"
    )
    text = extract_text(html, content_type="text/html")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert "SEXID" in lines[0]
    # Each valid-entry row survives as its own line (not a run-on blob), so the AI can read codes.
    assert any(ln.startswith("10") for ln in lines)
    assert any(ln.startswith("11") for ln in lines)
    assert any(ln.startswith("96") for ln in lines)


def test_plain_document_text_is_not_flagged():
    assert not looks_bot_blocked("YEAR: 2027/28\nADD FIELD SEXORT \"Sexual orientation\"")
