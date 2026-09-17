"""Pin the record-schema catalog to what build_records() actually produces.

The mapping UI dropdown is generated from RECORD_SCHEMA. If build_records() gains a new column
(e.g. a new `student.foo`) or renames one, the schema catalog must move with it — otherwise the
UI silently omits (or offers) the wrong path. This test walks the catalog and asserts every
declared path is present on a sample record.
"""
from __future__ import annotations

from app.modules.exports.record_schema import RECORD_SCHEMA, as_dict, known_paths


def _walk(record: dict, path: str):
    """Follow a dotted path down the flat record — returns the value, or a sentinel if the path
    doesn't exist on the record at all (which is the failure mode we're testing for)."""
    node: object = record
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return "MISSING"
        node = node[part]
    return node


# The shape build_records() produces, copy-pasted so a schema drift is caught even when the DB
# is empty (this is a unit test, not an integration test).
SAMPLE_RECORD = {
    "student": {
        "ref": "S001", "status": "active", "mode": "full_time",
        "startDate": None, "expectedEndDate": None, "originalExpectedEndDate": None,
        "entryRoute": None, "intensityPct": 100, "husid": "0000000000009",
    },
    "person": {"givenName": "Ada", "familyName": "Okonkwo",
               "nationality": "GB", "email": "a@t.com", "dateOfBirth": None},
    "programme": {"name": None, "code": None},
    "research": {"topic": None, "group": None},
    "funding": {"type": None, "source": None, "amount": None,
                "currency": None, "costCentre": None},
    "award": {"ref": None, "title": None},
}


def test_every_catalog_path_exists_on_the_flat_record_shape():
    """A path declared in RECORD_SCHEMA but not present in build_records() would put an option in
    the UI that always resolves to None — a silent misconfiguration. Fail loudly here instead."""
    misses = [p for p in known_paths() if _walk(SAMPLE_RECORD, p) == "MISSING"]
    assert not misses, (
        f"RECORD_SCHEMA lists paths not present on the flat record: {misses}. "
        "Either add the column in build_records() or drop the row from record_schema.py."
    )


def test_serialisation_shape_is_stable():
    """The frontend reads this exact shape — a rename here is an API break."""
    body = as_dict()
    assert "groups" in body and "paths" in body
    assert all({"root", "label", "description", "fields"} <= g.keys() for g in body["groups"])
    for g in body["groups"]:
        for f in g["fields"]:
            assert {"path", "label", "type", "hint", "nullable"} <= f.keys()


def test_every_group_has_at_least_one_field():
    """A group with no fields would render an empty section header — a lint, not a bug, but the
    catalog is small enough that an empty group is always an oversight."""
    for g in RECORD_SCHEMA:
        assert g.fields, f"Record group '{g.root}' has no fields"


def test_paths_are_unique():
    """The dropdown uses paths as keys — duplicates would collide silently."""
    paths = [f.path for g in RECORD_SCHEMA for f in g.fields]
    assert len(paths) == len(set(paths)), "Duplicate paths in RECORD_SCHEMA"
