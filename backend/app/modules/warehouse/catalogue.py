"""The warehouse contract: the T3 catalogue, described column by column.

The objects, their columns and which columns are personal data come from one place,
``app.db.tenant_views.CATALOGUE`` (the same contract as the per-institution reporting views), so
the reporting views, the scheduled files and the pull API always publish the same thing.

Every published row also carries ``_changed_at`` (when it last changed): the change column that
drives incremental extracts. Deletions are published separately (see ``extract.deleted``).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, Integer, Numeric, String, Text, Uuid

from app.db.tenant_views import CATALOGUE, Published

CHANGE_COLUMN = "updated_at"
CHANGE_FIELD = "_changed_at"

# Derived standard-view columns, computed in Python from a personal column (so they work on any
# database; the reporting views compute the same thing in SQL).
DERIVED = {"birth_year": ("date_of_birth", lambda v: v.year if v is not None else None)}


@dataclass(frozen=True)
class Column:
    name: str
    type: str          # string | integer | decimal | number | boolean | date | timestamp | json
    personal: bool = False
    description: str = ""


def _type_of(sa_type) -> str:
    if isinstance(sa_type, Boolean):
        return "boolean"
    if isinstance(sa_type, Integer):
        return "integer"
    if isinstance(sa_type, Numeric) and not isinstance(sa_type, Float):
        return "decimal"
    if isinstance(sa_type, Float):
        return "number"
    if isinstance(sa_type, DateTime):
        return "timestamp"
    if isinstance(sa_type, Date):
        return "date"
    if isinstance(sa_type, JSON):
        return "json"
    if isinstance(sa_type, (Uuid, String, Text, Enum)):
        return "string"
    return "string"


def _table(obj: Published):
    import app.db.registry  # noqa: F401  (every model on the metadata)
    from app.db.base import Base

    return Base.metadata.tables[obj.table]


def columns(obj: Published, personal: bool) -> list[Column]:
    """The published columns, in order, for the standard or the full-detail edition."""
    table = _table(obj)
    out = [Column(c, _type_of(table.c[c].type)) for c in obj.columns if c in table.c]
    if personal:
        out += [Column(c, _type_of(table.c[c].type), personal=True) for c in obj.personal if c in table.c]
    else:
        out += [Column(name, "integer", description=f"derived from {DERIVED[name][0]}")
                for name, _expr in obj.derived if name in DERIVED and DERIVED[name][0] in table.c]
    out.append(Column(CHANGE_FIELD, "timestamp", description="when the row last changed"))
    return out


def objects(names: list[str] | None = None) -> list[Published]:
    """Catalogue objects, all or the named ones (unknown names are an error)."""
    by_name = {o.name: o for o in CATALOGUE}
    if names is None:
        return list(CATALOGUE)
    unknown = sorted(set(names) - set(by_name))
    if unknown:
        raise ValueError(f"Unknown object(s): {', '.join(unknown)}")
    return [by_name[n] for n in names]


def describe(obj: Published, personal: bool) -> dict:
    """The object as the API and manifests describe it."""
    return {
        "name": obj.name,
        "description": obj.description,
        "key": "id",
        "changeColumn": CHANGE_FIELD,
        "columns": [{"name": c.name, "type": c.type, "personal": c.personal,
                     **({"description": c.description} if c.description else {})}
                    for c in columns(obj, personal)],
    }
