"""Object storage abstraction (arch §4, §13.3).

`LocalObjectStore` writes under `settings.storage_root` for dev; an S3/MinIO backend is a config
swap later (same interface). Keys are opaque, content-addressed by a random prefix so filenames
never collide and the original name is kept only as metadata on the `document` row.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings


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
        # Guard against path traversal: the resolved path must stay under root.
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage key")
        return p

    def save(self, data: bytes, *, suffix: str = "") -> tuple[str, str, int]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{uuid.uuid4().hex}{suffix}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key, digest, len(data)

    def open(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
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
