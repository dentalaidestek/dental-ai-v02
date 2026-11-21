"""Private, lazy-generated JPEG derivatives for clinical-media galleries.

The original remains immutable. The derivative key is deterministic so deletion
can enqueue cleanup without adding a database column or changing clinical rows.
"""
from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath
from threading import Lock
from PIL import Image, ImageOps, UnidentifiedImageError

from app import object_storage

THUMBNAIL_MAX_EDGE = 480
THUMBNAIL_JPEG_QUALITY = 78
THUMBNAIL_CONTENT_TYPE = "image/jpeg"


def thumbnail_reference(original_reference: str | Path) -> str:
    """Return a deterministic sibling key for the private thumbnail object."""
    raw = str(original_reference).replace("\\", "/")
    remote = raw.startswith("r2://")
    value = raw[5:] if remote else raw
    path = PurePosixPath(value)
    if not path.name or path.name in {".", ".."}:
        raise ValueError("Invalid clinical media reference")
    result = str(path.with_name(path.stem + ".thumb.jpg"))
    return "r2://" + result if remote else result


_locks_guard = Lock()
_locks: dict[str, tuple[Lock, int]] = {}


@contextmanager
def _generation_guard(reference: str):
    # Count holders and waiters so lock entries disappear after the final
    # caller. This avoids both duplicate cache-miss locks and unbounded growth.
    with _locks_guard:
        entry = _locks.get(reference)
        if entry is None:
            entry = (Lock(), 0)
        _locks[reference] = (entry[0], entry[1] + 1)
    try:
        with entry[0]:
            yield
    finally:
        with _locks_guard:
            current = _locks.get(reference)
            if current is not None and current[0] is entry[0]:
                if current[1] <= 1:
                    _locks.pop(reference, None)
                else:
                    _locks[reference] = (current[0], current[1] - 1)


def ensure_thumbnail(original_reference: str | Path) -> Path:
    """Materialize or create a bounded thumbnail; never mutate the original."""
    thumb_ref = thumbnail_reference(original_reference)
    try:
        return object_storage.ensure_local(thumb_ref)
    except FileNotFoundError:
        pass

    with _generation_guard(str(thumb_ref)):
        try:
            return object_storage.ensure_local(thumb_ref)
        except FileNotFoundError:
            pass

        original = object_storage.ensure_local(original_reference)
        try:
            with Image.open(original) as source:
                # Pillow 12 exif_transpose her zaman kopya döndürür ve format bilgisi düşer;
                # biçim kontrolü kapatılmamış kaynak üzerinde yapılır.
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported clinical image format")
                image = ImageOps.exif_transpose(source)
                image.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE), Image.Resampling.LANCZOS)
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY, optimize=True)
                payload = output.getvalue()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Clinical image cannot be decoded") from exc

        object_storage.write_bytes(thumb_ref, payload, content_type=THUMBNAIL_CONTENT_TYPE)
        return object_storage.ensure_local(thumb_ref)


def delete_thumbnail(original_reference: str | Path) -> None:
    """Delete only the derivative associated with this exact original key."""
    object_storage.delete(thumbnail_reference(original_reference))
