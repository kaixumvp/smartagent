from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import settings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalObjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, key: str, data: bytes) -> None:
        self._path(key).write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


class S3ObjectStore:
    """S3-compatible object store (MinIO / AWS S3). Uses the `minio` SDK lazily."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False) -> None:
        from minio import Minio

        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.bucket = bucket
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put(self, key: str, data: bytes) -> None:
        import io

        self.client.put_object(self.bucket, key, io.BytesIO(data), length=len(data))

    def get(self, key: str) -> bytes:
        response = None
        try:
            response = self.client.get_object(self.bucket, key)
            return response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def delete(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)


def build_store() -> ObjectStore:
    if settings.object_store_type == "s3":
        if not settings.s3_endpoint_url:
            raise ValueError("S3_ENDPOINT_URL is required when OBJECT_STORE_TYPE=s3")
        return S3ObjectStore(
            settings.s3_endpoint_url,
            settings.s3_access_key,
            settings.s3_secret_key,
            settings.s3_bucket,
            settings.s3_secure,
        )
    return LocalObjectStore(settings.object_store_dir)
