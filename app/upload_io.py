"""Bounded image copy; failed intake never leaves a partial temporary upload."""
from pathlib import Path
from starlette.exceptions import HTTPException


def copy_image(source, destination, *, maximum=25 * 1024 * 1024):
    destination = Path(destination)
    total = 0
    try:
        with destination.open('wb') as output:
            while block := source.read(1024 * 1024):
                total += len(block)
                if total > maximum:
                    raise HTTPException(413, 'Bir görüntü en fazla 25 MB olabilir.')
                output.write(block)
        if not total:
            raise HTTPException(400, 'Boş görüntü yüklenemez.')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
