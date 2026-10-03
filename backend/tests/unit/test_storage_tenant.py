"""T4 — stored files are partitioned by institution, and a key from one institution can't be
opened or deleted while acting as another (second lock behind the RLS-scoped document row)."""
from __future__ import annotations

import uuid

import pytest

from app.core.errors import NotFoundError
from app.core.storage import LocalObjectStore, content_disposition, tenant_of_key
from app.core.tenant_context import system_scope, tenant_scope

A = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
B = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def test_keys_carry_the_acting_institution(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    with tenant_scope(A):
        key, _, size = store.save(b"thesis", suffix=".pdf")
    assert tenant_of_key(key) == str(A) and key.endswith(".pdf") and size == 6
    assert (tmp_path / str(A)).is_dir()


def test_another_institutions_key_reads_as_not_found(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    with tenant_scope(A):
        key, _, _ = store.save(b"secret")
        assert store.open(key) == b"secret"
    with tenant_scope(B):
        with pytest.raises(NotFoundError):
            store.open(key)
        with pytest.raises(NotFoundError):
            store.delete(key)
    with pytest.raises(NotFoundError):          # no institution at all
        store.open(key)
    with tenant_scope(A):
        assert store.open(key) == b"secret"     # B's delete attempt removed nothing


def test_tooling_bypass_and_pre_t4_keys_still_work(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    with tenant_scope(A):
        key, _, _ = store.save(b"x")
    with system_scope():
        assert store.open(key) == b"x"
    (tmp_path / "legacy.txt").write_bytes(b"old")
    with tenant_scope(B):
        assert tenant_of_key("legacy.txt") is None
        assert store.open("legacy.txt") == b"old"


@pytest.mark.parametrize("key", ["../outside.txt", "../storage2/x", "..\\x"])
def test_keys_cannot_escape_the_root(tmp_path, key):
    store = LocalObjectStore(str(tmp_path / "storage"))
    with pytest.raises(ValueError):
        store._path(key)


def test_download_filenames_are_made_safe():
    header = content_disposition('evil".pdf\r\nX-Injected: 1')
    assert "\r" not in header and "\n" not in header
    assert header.startswith('attachment; filename="evil_.pdf__X-Injected: 1"')
    assert "filename*=UTF-8''evil%22.pdf%0D%0AX-Injected%3A%201" in header
    assert content_disposition("résumé.pdf", "inline").startswith('inline; filename="r_sum_.pdf"')
    assert content_disposition(None).startswith('attachment; filename="download"')


def test_each_institution_has_its_own_webhook_secret():
    """T4 — a partner holding one institution's secret can't sign for another."""
    from app.core.config import get_settings
    from app.core.inbound import sign, webhook_secret
    from app.core.tenant_context import DEFAULT_TENANT_ID

    assert webhook_secret(DEFAULT_TENANT_ID) == get_settings().app_secret_key.encode()  # unchanged
    assert len({webhook_secret(t) for t in (DEFAULT_TENANT_ID, A, B)}) == 3
    assert sign(A, b"{}") != sign(B, b"{}")
