"""Bounded upload helpers; failed intake never leaves a partial temporary upload."""
from pathlib import Path
from starlette.exceptions import HTTPException

from app.upload_limits import (
    MAX_ANALYSIS_IMAGE_BYTES,
)


def upload_size(source) -> int:
    """Return the actual parsed/spooled byte count, never a client header value."""
    size = getattr(source, "size", None)
    if isinstance(size, int) and size >= 0:
        return size
    stream = getattr(source, "file", source)
    try:
        position = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(position)
    except (AttributeError, OSError, ValueError) as exc:
        raise HTTPException(400, "Yüklenen dosyanın gerçek boyutu doğrulanamadı.") from exc
    if not isinstance(size, int) or size < 0:
        raise HTTPException(400, "Yüklenen dosyanın gerçek boyutu doğrulanamadı.")
    return size


def validate_upload_batch(sources, *, maximum_file: int, maximum_total: int) -> int:
    """Preflight real file sizes before creating records or copying any bytes."""
    total = 0
    for source in sources:
        size = upload_size(source)
        if size < 1:
            raise HTTPException(400, "Boş görüntü yüklenemez.")
        if size > maximum_file:
            raise HTTPException(413, f"Bir görüntü en fazla {maximum_file // (1024 * 1024)} MiB olabilir.")
        total += size
        if total > maximum_total:
            raise HTTPException(413, f"Toplam görüntü boyutu en fazla {maximum_total // (1024 * 1024)} MiB olabilir.")
    return total


def validate_path_batch(paths, *, maximum_file: int, maximum_total: int) -> int:
    """Bound existing private media before staging it for a new analysis."""
    total = 0
    for path in paths:
        try:
            size = Path(path).stat().st_size
        except OSError as exc:
            raise HTTPException(404, "Seçilen klinik görüntü dosyası bulunamadı.") from exc
        if size < 1:
            raise HTTPException(422, "Boş klinik görüntü analiz edilemez.")
        if size > maximum_file:
            raise HTTPException(413, f"Kayıtlı bir görüntü en fazla {maximum_file // (1024 * 1024)} MiB olabilir.")
        total += size
        if total > maximum_total:
            raise HTTPException(413, f"Kayıtlı ve yeni görüntülerin toplamı en fazla {maximum_total // (1024 * 1024)} MiB olabilir.")
    return total


def copy_image(source, destination, *, maximum=MAX_ANALYSIS_IMAGE_BYTES):
    """Copy in bounded chunks and remove partial output on every failure."""
    destination = Path(destination)
    total = 0
    try:
        with destination.open("wb") as output:
            while block := source.read(1024 * 1024):
                total += len(block)
                if total > maximum:
                    raise HTTPException(413, f"Bir görüntü en fazla {maximum // (1024 * 1024)} MiB olabilir.")
                output.write(block)
        if not total:
            raise HTTPException(400, "Boş görüntü yüklenemez.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
