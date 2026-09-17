"""Pin the transforms catalog to the actual transform functions.

A transform in statutory.TRANSFORMS without an entry in transforms_catalog.CATALOG would render
in the mapping picker as a raw code name (or not at all if the picker is catalog-driven). And a
catalog entry pointing at a transform that no longer exists would leak into the picker as an
option that silently no-ops on Generate. Either drift is a real bug — this test catches both.
"""
from __future__ import annotations

from app.modules.exports.statutory import TRANSFORMS
from app.modules.exports.transforms_catalog import CATALOG, as_dict, known_names


def test_every_registered_transform_has_a_catalog_entry():
    catalog = known_names()
    missing = sorted(set(TRANSFORMS) - catalog)
    assert not missing, (
        f"These transforms are registered in TRANSFORMS but have no human-facing catalog entry: "
        f"{missing}. Add them to transforms_catalog.CATALOG so the mapping picker can label them."
    )


def test_no_catalog_entries_reference_missing_transforms():
    stray = sorted(known_names() - set(TRANSFORMS))
    assert not stray, (
        f"These catalog entries name transforms that no longer exist in TRANSFORMS: "
        f"{stray}. Drop them from transforms_catalog.CATALOG."
    )


def test_serialisation_shape():
    body = as_dict()
    assert "categories" in body and "names" in body
    for cat in body["categories"]:
        assert {"category", "transforms"} <= cat.keys()
        for t in cat["transforms"]:
            assert {"name", "category", "label", "description"} <= t.keys()


def test_every_catalog_entry_has_a_description():
    """A blank description is worse than no entry — the picker would say 'strip_name — ' with
    nothing after the em-dash. Lint against empty strings here."""
    for t in CATALOG:
        assert t["label"].strip(), f"Transform '{t['name']}' has no label"
        assert t["description"].strip(), f"Transform '{t['name']}' has no description"
