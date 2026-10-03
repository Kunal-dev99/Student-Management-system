"""Write published rows as Parquet or CSV, typed from the catalogue.

Parquet carries the schema (dates as dates, timestamps in UTC, decimals exact), which is what
warehouses load best. CSV is the fallback: UTF-8, a header row, ISO-8601 dates and timestamps,
JSON values as JSON text, empty for null.
"""
from __future__ import annotations

import csv
import decimal
import io
import json
import uuid
from datetime import date, datetime

from app.modules.warehouse.catalogue import Column

FORMATS = ("parquet", "csv")


def _plain(value, type_: str):
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):   # enums
        return value.value
    if type_ == "json":
        return json.dumps(value, default=str, separators=(",", ":"))
    if type_ == "decimal":
        return decimal.Decimal(str(value))
    if type_ == "string" and not isinstance(value, str):
        return str(value)
    return value


def to_csv(rows: list[dict], cols: list[Column]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([c.name for c in cols])
    for r in rows:
        out = []
        for c in cols:
            v = _plain(r.get(c.name), c.type)
            if v is None:
                out.append("")
            elif isinstance(v, (datetime, date)):
                out.append(v.isoformat())
            elif isinstance(v, bool):
                out.append("true" if v else "false")
            else:
                out.append(v)
        w.writerow(out)
    return buf.getvalue().encode("utf-8")


def _arrow_type(c: Column):
    import pyarrow as pa

    return {
        "string": pa.string(), "integer": pa.int64(), "number": pa.float64(), "boolean": pa.bool_(),
        "date": pa.date32(), "timestamp": pa.timestamp("us", tz="UTC"), "json": pa.string(),
        "decimal": pa.decimal128(38, 9),
    }[c.type]


def to_parquet(rows: list[dict], cols: list[Column]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([pa.field(c.name, _arrow_type(c), nullable=True,
                                 metadata={"personal": "true" if c.personal else "false"}) for c in cols])
    data = {c.name: [_plain(r.get(c.name), c.type) for r in rows] for c in cols}
    table = pa.Table.from_pydict(data, schema=schema)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()


def write(rows: list[dict], cols: list[Column], fmt: str) -> bytes:
    if fmt == "parquet":
        return to_parquet(rows, cols)
    if fmt == "csv":
        return to_csv(rows, cols)
    raise ValueError(f"Unknown format {fmt!r}; use one of {FORMATS}")


DELETED_COLUMNS = [Column("id", "string"), Column("deleted_at", "timestamp")]
