"""DW-4 — publishing to OCI Object Storage through its S3-compatible API (boto3, stubbed: no
network). The manifest goes last, every key is under the institution's prefix, and the client is
configured the way OCI needs (custom endpoint, path-style addressing)."""
from __future__ import annotations

import pytest
from botocore.stub import ANY, Stubber

from app.core.config import get_settings
from app.modules.warehouse.targets import LocalTarget, S3Target, default_target

OCI = "https://mynamespace.compat.objectstorage.uk-london-1.oraclecloud.com"


def _target(prefix=""):
    t = S3Target(endpoint=OCI, region="uk-london-1", bucket="pgr-warehouse",
                 access_key="AKIA-TEST", secret_key="secret-test", prefix=prefix)
    return t, Stubber(t.client)


def test_puts_land_in_the_bucket_under_the_institution_prefix():
    t, stub = _target(prefix="exports")
    stub.add_response("put_object", {}, {"Bucket": "pgr-warehouse", "Key": "exports/icr/nightly/run/student.parquet",
                                         "Body": b"data", "ContentType": "application/vnd.apache.parquet"})
    stub.add_response("put_object", {}, {"Bucket": "pgr-warehouse", "Key": "exports/icr/nightly/run/manifest.json",
                                         "Body": ANY, "ContentType": "application/json"})
    with stub:
        assert t.put("icr/nightly/run/student.parquet", b"data", "application/vnd.apache.parquet") == \
            "s3://pgr-warehouse/exports/icr/nightly/run/student.parquet"
        t.put("icr/nightly/run/manifest.json", b"{}", "application/json")
        stub.assert_no_pending_responses()
    assert t.location("icr/nightly/run") == "s3://pgr-warehouse/exports/icr/nightly/run"


def test_client_is_configured_for_oci():
    t, _ = _target()
    assert t.client.meta.endpoint_url == OCI
    assert t.client.meta.config.s3["addressing_style"] == "path"
    assert t.client.meta.region_name == "uk-london-1"
    assert t.client.meta.config.request_checksum_calculation == "when_required"


def test_default_target_follows_settings(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "warehouse_target", "local")
    monkeypatch.setattr(s, "warehouse_local_root", str(tmp_path))
    assert isinstance(default_target(), LocalTarget)
    monkeypatch.setattr(s, "warehouse_target", "s3")
    monkeypatch.setattr(s, "warehouse_s3_bucket", None)
    with pytest.raises(RuntimeError, match="WAREHOUSE_S3_BUCKET"):
        default_target()
    monkeypatch.setattr(s, "warehouse_s3_bucket", "pgr-warehouse")
    monkeypatch.setattr(s, "warehouse_s3_endpoint", OCI)
    assert isinstance(default_target(), S3Target)


def test_local_target_refuses_keys_outside_its_root(tmp_path):
    t = LocalTarget(str(tmp_path / "wh"))
    with pytest.raises(ValueError):
        t.put("../escape.txt", b"x")
