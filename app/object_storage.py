"""Private object storage with a local-development fallback.

Production enables Cloudflare R2 explicitly with ``R2_ENABLED=1``.  Stored
database references remain normal ``uploads/...`` paths for compatibility;
the same path is used as the private R2 object key.  A local file is retained
as a short-lived cache so existing image/PDF processing code can keep using
``pathlib.Path``.
"""

from __future__ import annotations

import mimetypes
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


class ObjectStorageError(RuntimeError):
    """Raised when configured persistent storage is unavailable."""


def enabled() -> bool:
    return os.getenv("R2_ENABLED", "0").strip() == "1"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ObjectStorageError(f"{name} is required when R2_ENABLED=1")
    return value


@lru_cache(maxsize=1)
def _settings() -> tuple[str, str, str, str]:
    return (
        _required("R2_BUCKET_NAME"),
        _required("R2_ENDPOINT_URL").rstrip("/"),
        _required("R2_ACCESS_KEY_ID"),
        _required("R2_SECRET_ACCESS_KEY"),
    )


@lru_cache(maxsize=1)
def _client():
    if not enabled():
        raise ObjectStorageError("R2 object storage is not enabled")
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise ObjectStorageError("boto3 is required when R2 is enabled") from exc

    bucket, endpoint, access_key, secret_key = _settings()
    del bucket
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _object_key(reference: str | Path) -> str:
    raw = str(reference).replace("\\", "/").strip()
    if raw.startswith("r2://"):
        raw = raw[5:]
    marker = "/uploads/"
    if marker in raw:
        raw = "uploads/" + raw.split(marker, 1)[1]
    raw = raw.lstrip("/")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if not parts or ".." in parts:
        raise ObjectStorageError("Invalid object storage path")
    return "/".join(parts)


def _local_path(reference: str | Path) -> Path:
    raw = str(reference)
    if raw.startswith("r2://"):
        return Path(_object_key(reference))
    return Path(raw)


def check_connection() -> None:
    """Fail startup when production storage credentials/bucket are invalid."""
    if not enabled():
        return
    bucket, _, _, _ = _settings()
    try:
        _client().list_objects_v2(Bucket=bucket, MaxKeys=1)
    except Exception as exc:
        raise ObjectStorageError("R2 bucket connection check failed") from exc


def persist_file(
    path: str | Path,
    *,
    content_type: Optional[str] = None,
) -> str:
    """Upload an existing local file and return its compatible DB reference."""
    local = _local_path(path)
    if not local.is_file():
        raise ObjectStorageError(f"Local file does not exist: {local}")
    if not enabled():
        return str(local)
    bucket, _, _, _ = _settings()
    key = _object_key(local)
    guessed = content_type or mimetypes.guess_type(local.name)[0]
    extra = {"ContentType": guessed} if guessed else None
    try:
        if extra:
            _client().upload_file(str(local), bucket, key, ExtraArgs=extra)
        else:
            _client().upload_file(str(local), bucket, key)
    except Exception as exc:
        raise ObjectStorageError(f"R2 upload failed for {key}") from exc
    return str(local)


def write_bytes(
    path: str | Path,
    data: bytes,
    *,
    content_type: Optional[str] = None,
) -> str:
    local = _local_path(path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    return persist_file(local, content_type=content_type)


def write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> str:
    return write_bytes(path, text.encode(encoding), content_type="application/json")


def exists(reference: str | Path | None) -> bool:
    if not reference:
        return False
    local = _local_path(reference)
    if local.is_file():
        return True
    if not enabled():
        return False
    bucket, _, _, _ = _settings()
    try:
        _client().head_object(Bucket=bucket, Key=_object_key(reference))
        return True
    except Exception:
        return False


def size(reference: str | Path | None) -> int:
    if not reference:
        return 0
    local = _local_path(reference)
    if local.is_file():
        return local.stat().st_size
    if not enabled():
        return 0
    bucket, _, _, _ = _settings()
    try:
        result = _client().head_object(Bucket=bucket, Key=_object_key(reference))
        return int(result.get("ContentLength") or 0)
    except Exception:
        return 0


def ensure_local(reference: str | Path) -> Path:
    """Return a readable local cache path, downloading from R2 when needed."""
    local = _local_path(reference)
    if local.is_file():
        return local
    if not enabled():
        raise FileNotFoundError(str(local))
    bucket, _, _, _ = _settings()
    local.parent.mkdir(parents=True, exist_ok=True)
    temporary = local.with_name(f".{local.name}.downloading")
    try:
        _client().download_file(bucket, _object_key(reference), str(temporary))
        temporary.replace(local)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise FileNotFoundError(str(reference)) from exc
    return local


def delete(reference: str | Path | None) -> None:
    if not reference:
        return
    local = _local_path(reference)
    local.unlink(missing_ok=True)
    if enabled():
        bucket, _, _, _ = _settings()
        try:
            _client().delete_object(Bucket=bucket, Key=_object_key(reference))
        except Exception as exc:
            raise ObjectStorageError("R2 delete failed") from exc
