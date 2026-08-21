"""Pagination helpers and the standard list envelope (arch §11.2, §11.3)."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from fastapi import Query

T = TypeVar("T")

DEFAULT_LIMIT = 25
MAX_LIMIT = 200


@dataclass
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0
    cursor: str | None = None


def page_params(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    cursor: str | None = Query(None),
) -> PageParams:
    return PageParams(limit=limit, offset=offset, cursor=cursor)


def encode_cursor(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


def list_envelope(
    data: Sequence[T], *, limit: int, total: int | None = None, next_cursor: str | None = None
) -> dict:
    """`{ "data": [...], "page": { "limit", "nextCursor", "total" } }`."""
    return {
        "data": list(data),
        "page": {"limit": limit, "nextCursor": next_cursor, "total": total},
    }
