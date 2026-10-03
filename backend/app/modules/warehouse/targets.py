"""Where published files go: a local folder, or an S3-compatible bucket (OCI Object Storage).

Every key starts with the institution's prefix (``<subdomain>/...``), so one bucket can hold every
institution's publications and a bucket policy, lifecycle rule or consumer grant can target one.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


class LocalTarget:
    kind = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("Invalid key")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return str(p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def location(self, prefix: str) -> str:
        return str(self._path(prefix))


class S3Target:
    """OCI Object Storage (or S3, MinIO) through the S3-compatible API."""
    kind = "s3"

    def __init__(self, *, endpoint: str | None, region: str | None, bucket: str,
                 access_key: str | None, secret_key: str | None, prefix: str = "", client=None) -> None:
        self.bucket, self.prefix = bucket, prefix.strip("/")
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3", endpoint_url=endpoint, region_name=region,
                aws_access_key_id=access_key, aws_secret_access_key=secret_key,
                # OCI's S3-compatible endpoint needs path-style addressing, and (like other
                # S3-compatible stores) may not accept the checksums newer boto3 adds by default.
                config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5},
                              request_checksum_calculation="when_required",
                              response_checksum_validation="when_required"),
            )
        self.client = client

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=content_type)
        return f"s3://{self.bucket}/{self._key(key)}"

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()

    def location(self, prefix: str) -> str:
        return f"s3://{self.bucket}/{self._key(prefix)}"


def default_target():
    s = get_settings()
    if s.warehouse_target == "s3":
        if not s.warehouse_s3_bucket:
            raise RuntimeError("WAREHOUSE_TARGET=s3 needs WAREHOUSE_S3_BUCKET (and endpoint and keys)")
        return S3Target(endpoint=s.warehouse_s3_endpoint, region=s.warehouse_s3_region,
                        bucket=s.warehouse_s3_bucket, access_key=s.warehouse_s3_access_key,
                        secret_key=s.warehouse_s3_secret_key, prefix=s.warehouse_s3_prefix)
    return LocalTarget(s.warehouse_local_root)
