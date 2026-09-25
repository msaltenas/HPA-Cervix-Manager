"""Convert downloaded HPA images into real JPEG files.

`convert_to_jpeg` always round-trips the bytes through Pillow and re-encodes
them as JPEG -- it never just renames/copies a file with a different
extension. The original downloaded bytes are kept in memory only; only the
converted JPEG is written to disk, so there is no separate "original" file
to accidentally overwrite.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

JPEG_QUALITY = 95


@dataclass(frozen=True)
class ConversionResult:
    width: int
    height: int
    original_format: str
    file_size: int


def convert_to_jpeg(image_bytes: bytes, destination: Path) -> ConversionResult:
    """Decode arbitrary image bytes with Pillow and save as a real JPEG.

    Handles alpha/transparency by compositing onto a white background,
    since JPEG has no alpha channel. Raises PIL.UnidentifiedImageError if
    the bytes are not a decodable image (never silently writes garbage).
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        original_format = img.format or "UNKNOWN"
        width, height = img.size

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            rgb_image = background
        else:
            rgb_image = img.convert("RGB")

        destination.parent.mkdir(parents=True, exist_ok=True)
        rgb_image.save(destination, format="JPEG", quality=JPEG_QUALITY)

    file_size = destination.stat().st_size
    return ConversionResult(
        width=width,
        height=height,
        original_format=original_format,
        file_size=file_size,
    )
