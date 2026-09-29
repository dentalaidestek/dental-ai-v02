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
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
import threading
import time
from typing import Optional
import uuid
from app import object_cache


class ObjectStorageError(RuntimeError):
    """Raised when configured persistent storage is unavailable."""


_SIZE_CACHE: OrderedDict[str, tuple[float, int]] = OrderedDict()
_SIZE_CACHE_LOCK = threading.Lock()
_SIZE_CACHE_TTL_SECONDS = 600
_SIZE_CACHE_MAX_ITEMS = 4096


def _cached_size(key: str) -> int | None:
    now = time.monotonic()
    with _SIZE_CACHE_LOCK:
        item = _SIZE_CACHE.get(key)
        if item is None:
            return None
        created_at, value = item
        if now - created_at > _SIZE_CACHE_TTL_SECONDS:
            _SIZE_CACHE.pop(key, None)
            return None
        _SIZE_CACHE.move_to_end(key)
        return value


def _remember_size(key: str, value: int) -> None:
    with _SIZE_CACHE_LOCK:
        _SIZE_CACHE[key] = (time.monotonic(), max(0, int(value)))
        _SIZE_CACHE.move_to_end(key)
        while len(_SIZE_CACHE) > _SIZE_CACHE_MAX_ITEMS:
            _SIZE_CACHE.popitem(last=False)


def _forget_size(key: str) -> None:
    with _SIZE_CACHE_LOCK:
        _SIZE_CACHE.pop(key, None)


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
    from boto3.s3.transfer import TransferConfig
    transfer = TransferConfig(use_threads=False, max_concurrency=1)
    try:
        if extra:
            _client().upload_file(str(local), bucket, key, ExtraArgs=extra, Config=transfer)
        else:
            _client().upload_file(str(local), bucket, key, Config=transfer)
    except Exception as exc:
        raise ObjectStorageError(f"R2 upload failed for {key}") from exc
    object_cache.invalidate(key)
    _remember_size(key, local.stat().st_size)
    object_cache.uploaded(local)
    return str(local)


def write_bytes(
    path: str | Path,
    data: bytes,
    *,
    content_type: Optional[str] = None,
) -> str:
    local = _local_path(path)
    local.parent.mkdir(parents=True, exist_ok=True)
    temporary = local.with_name(f".{local.name}.{uuid.uuid4().hex}.writing")
    try:
        temporary.write_bytes(data)
        temporary.replace(local)
    finally:
        temporary.unlink(missing_ok=True)
    return persist_file(local, content_type=content_type)


def write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> str:
    return write_bytes(path, text.encode(encoding), content_type="application/json")


def _is_missing(exc):
    response = getattr(exc, "response", {})
    return str(response.get("Error", {}).get("Code", "")) in {"404", "NoSuchKey", "NotFound"}


def exists(reference: str | Path | None) -> bool:
    if not reference:
        return False
    local = _local_path(reference)
    if local.is_file() and not enabled():
        return True
    if not enabled():
        return False
    bucket, _, _, _ = _settings()
    try:
        _client().head_object(Bucket=bucket, Key=_object_key(reference))
        return True
    except Exception as exc:
        if _is_missing(exc):
            return False
        raise ObjectStorageError("R2 metadata unavailable") from exc


def size(reference: str | Path | None) -> int:
    if not reference:
        return 0
    local = _local_path(reference)
    if local.is_file() and not enabled():
        return local.stat().st_size
    if not enabled():
        return 0
    bucket, _, _, _ = _settings()
    key = _object_key(reference)
    cached = _cached_size(key)
    if cached is not None:
        return cached
    try:
        result = _client().head_object(Bucket=bucket, Key=key)
        value = int(result.get("ContentLength") or 0)
        _remember_size(key, value)
        return value
    except Exception as exc:
        if _is_missing(exc):
            return 0
        raise ObjectStorageError("R2 metadata unavailable") from exc


def ensure_local(reference: str | Path) -> Path:
    """Materialize private remote objects within the caller's reader scope."""
    local = _local_path(reference)
    if not enabled():
        if local.is_file():
            return local
        raise FileNotFoundError(str(local))
    bucket, _, _, _ = _settings()
    key = _object_key(reference)

    def metadata():
        try:
            return _client().head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if _is_missing(exc):
                raise FileNotFoundError(str(reference)) from exc
            raise ObjectStorageError("R2 metadata unavailable") from exc

    def download(destination, expected_size):
        # Stream synchronously with bounded buffers, never boto3's multipart
        # thread pool or an unbounded read into RAM.
        try:
            result = _client().get_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if _is_missing(exc):
                raise FileNotFoundError(str(reference)) from exc
            raise ObjectStorageError("R2 download unavailable") from exc
        body = result['Body']
        total = 0
        try:
            with destination.open('wb') as output:
                while chunk := body.read(1024 * 1024):
                    total += len(chunk)
                    if total > expected_size:
                        raise ObjectStorageError('R2 object changed during download')
                    output.write(chunk)
        finally:
            body.close()

    return object_cache.materialize(
        key,
        metadata=metadata,
        download=download,
    )


def delete(reference: str | Path | None) -> None:
    if not reference:
        return
    local = _local_path(reference)
    key = _object_key(reference) if enabled() else None
    if enabled():
        bucket, _, _, _ = _settings()
        try:
            _client().delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise ObjectStorageError("R2 delete failed") from exc

    if key is not None:
        object_cache.invalidate(key)
        _forget_size(key)
    local.unlink(missing_ok=True)
