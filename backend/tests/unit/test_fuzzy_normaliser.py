"""CB-A — Unit tests for the query normaliser (Layer 1)."""
from __future__ import annotations

import pytest

from app.modules.fuzzy.normaliser import normalise


@pytest.mark.parametrize("raw,expected_tokens", [
    ("Show me held payments", ["show", "held", "payments"]),
    ("please could you list overdue stipends", ["list", "overdue", "stipends"]),
    ("who's late paying?", ["who", "late", "paying"]),
    # Contractions expand and negation survives; "have"/"been" drop as fillers.
    ("students who haven't been seen", ["students", "who", "not", "seen"]),
    # Politeness fillers dropped, verb kept.
    ("just show me alice", ["show", "alice"]),
    # Time phrases become sentinels.
    ("held payments this quarter", ["held", "payments", "period_thisquarter"]),
    ("cashflow ytd", ["cashflow", "period_thisyear"]),
    # Punctuation collapsed.
    ("what?!.  overdue,  payments", ["what", "overdue", "payments"]),
])
def test_normalise_produces_expected_tokens(raw, expected_tokens):
    out = normalise(raw)
    assert list(out.tokens) == expected_tokens


def test_normalise_preserves_original():
    out = normalise("Show me Alice")
    assert out.original == "Show me Alice"
    assert "alice" in out.tokens


def test_empty_query_returns_empty_tokens():
    out = normalise("")
    assert out.tokens == ()
    assert out.text == ""
