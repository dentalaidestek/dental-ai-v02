from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageStat

VALID_MODALITIES = {"PANORAMIC", "BITEWING", "PERIAPICAL", "INTRAORAL_PHOTO"}

def classify_dental_image(path: str) -> str:
    """Fast local modality routing. It does not diagnose; it only selects a motor family."""
    p = Path(path)
    with Image.open(p) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w < 1 or h < 1:
            raise ValueError("Geçersiz görüntü boyutu")
        thumb = im.copy()
        thumb.thumbnail((256, 256))
        stat = ImageStat.Stat(thumb)
        means = stat.mean[:3]
        channel_spread = max(means) - min(means)
        extrema = thumb.getextrema()
        color_range_spread = max(x[1] - x[0] for x in extrema) - min(x[1] - x[0] for x in extrema)
        ratio = w / h

        # Clinical intraoral photographs retain meaningful RGB chroma. Dental
        # radiographs are effectively grayscale even when stored as RGB JPEG/PNG.
        if channel_spread >= 10.0 or color_range_spread >= 18.0:
            return "INTRAORAL_PHOTO"

        # Panoramics are characteristically much wider than they are tall.
        if ratio >= 1.75:
            return "PANORAMIC"

        # Bitewings are normally landscape; periapicals are commonly portrait
        # or close to square. This is intentionally only a routing heuristic.
        if ratio >= 1.12:
            return "BITEWING"
        return "PERIAPICAL"
