"""T3 — the published view catalogue matches the models and keeps personal data out of the
standard views. No database needed, so this guards every build."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import Text

import app.main  # noqa: F401  (registers every model)
from app.db.base import Base
from app.db.tenant_views import CATALOGUE, reporting_roles, schemas, slug

# Column names that suggest personal data or free text. A standard-view column matching one of
# these must be listed below with the reason it is not personal.
_PERSONAL_HINT = re.compile(r"name|email|birth|phone|address|passport|nino|ni_number|note|reason|bio|ref$")
_NOT_PERSONAL = {
    ("programme", "name"): "programme title",
    ("department", "name"): "department title",
    ("funding_source", "name"): "funder organisation",
    ("unit_of_assessment", "name"): "REF unit title",
    ("student", "student_ref"): "institution's own student number, the key reporting joins on",
    ("student_lifecycle_event", "leaver_reason"): "HESA leaver reason code (32 chars), not free text",
}


def test_catalogue_names_are_unique():
    names = [o.name for o in CATALOGUE]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("obj", CATALOGUE, ids=lambda o: o.name)
def test_every_published_column_exists_on_a_tenant_table(obj):
    table = Base.metadata.tables.get(obj.table)
    assert table is not None, f"{obj.name}: no table {obj.table}"
    assert "tenant_id" in table.c, f"{obj.name}: {obj.table} isn't tenant-owned"
    missing = [c for c in obj.columns + obj.personal if c not in table.c]
    assert missing == [], f"{obj.name}: {obj.table} has no {missing}"
    assert not set(obj.columns) & set(obj.personal), f"{obj.name}: a column is both standard and personal"
    assert "tenant_id" not in obj.columns + obj.personal


@pytest.mark.parametrize("obj", CATALOGUE, ids=lambda o: o.name)
def test_standard_views_carry_no_personal_data_or_free_text(obj):
    table = Base.metadata.tables[obj.table]
    flagged = [
        c for c in obj.columns
        if (_PERSONAL_HINT.search(c) or isinstance(table.c[c].type, Text))
        and (obj.table, c) not in _NOT_PERSONAL
    ]
    assert flagged == [], (
        f"{obj.name}: {flagged} look personal or free text. Move them to `personal`, "
        "or add them to _NOT_PERSONAL with the reason they are safe."
    )


def test_names_are_derived_safely():
    assert schemas("icr") == ("tenant_icr", "tenant_icr_full")
    assert reporting_roles("St-Andrews") == ("st_andrews_reporting", "st_andrews_reporting_full")
    # Only [a-z0-9_] survive, so a subdomain can never inject into DDL.
    assert slug('icr"; DROP TABLE student; --') == "icr_drop_table_student"
    with pytest.raises(ValueError):
        slug("!!!")
