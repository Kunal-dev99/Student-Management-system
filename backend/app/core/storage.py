"""Object storage abstraction (arch §4, §13.3).

`LocalObjectStore` writes under `settings.storage_root` for dev; an S3/MinIO backend is a config
swap later (same interface). Keys are opaque, content-addressed by a random prefix so filenames
never collide and the original name is kept only as metadata on the `document` row.

T4 — keys are ``<tenant id>/<random>.<ext>``: each institution's files live under their own
prefix (a bucket policy, purge or export can target one institution), and ``open``/``delete``
refuse a key whose prefix isn't the acting institution, as a second lock behind the RLS-scoped
``document`` row that every download loads first. Keys from before T4 have no prefix and stay
readable.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.tenant_context import get_current_tenant, is_tenant_bypass, resolve_tenant_for_write


def tenant_of_key(key: str) -> str | None:
    """The institution a key belongs to, or None for a pre-T4 key."""
    head, sep, _ = key.partition("/")
    return head if sep else None


def _check_tenant(key: str) -> None:
    owner = tenant_of_key(key)
    if owner is None or is_tenant_bypass():
        return
    acting = get_current_tenant()
    if acting is None or str(acting) != owner:
        # Same answer as a missing file: don't confirm another institution's key exists.
        raise NotFoundError("File not found")


class ObjectStore(ABC):
    @abstractmethod
    def save(self, data: bytes, *, suffix: str = "") -> tuple[str, str, int]:
        """Store bytes; return (key, sha256_hex, size)."""

    @abstractmethod
    def open(self, key: str) -> bytes:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...


class LocalObjectStore(ObjectStore):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        # Guard against path traversal: the resolved path must stay under root (a real
        # containment check, not a string prefix, which a sibling like "storage2" would pass).
        if not p.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid storage key")
        return p

    def save(self, data: bytes, *, suffix: str = "") -> tuple[str, str, int]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{resolve_tenant_for_write()}/{uuid.uuid4().hex}{suffix}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key, digest, len(data)

    def open(self, key: str) -> bytes:
        _check_tenant(key)
        with open(self._path(key), "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        _check_tenant(key)
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        settings = get_settings()
        # Only the local backend is wired here; s3 falls back to local until the S3 client lands.
        _store = LocalObjectStore(settings.storage_root)
    return _store


def content_disposition(filename: str | None, kind: str = "attachment") -> str:
    """A safe Content-Disposition header for a user-supplied filename: an ASCII fallback with
    quotes, backslashes and control characters removed, plus the exact name RFC 5987-encoded."""
    import re
    from urllib.parse import quote

    name = filename or "download"
    ascii_name = re.sub(r'[^\x20-\x7e]|["\\]', "_", name)[:150] or "download"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name[:150], safe='')}"
