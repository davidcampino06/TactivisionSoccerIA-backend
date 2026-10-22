"""Team crest images: every upload is decoded and drawn again as a clean 256 px PNG.

Re-encoding (instead of storing what was uploaded) drops metadata (GPS, camera), anything hidden
after the image data and any script: only PNG, JPEG and WebP are accepted (no SVG, which can carry
JavaScript), the size is checked before and after, and huge pixel counts are refused before
decoding (decompression bombs).
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

CREST_SIZE = 256
MAX_UPLOAD_BYTES = 2 * 1024 * 1024        # what the coach may upload
MAX_STORED_BYTES = 300_000                # what the database accepts (migration 0015)
MAX_PIXELS = 25_000_000                   # refuse e.g. a 30000 x 30000 PNG before decoding it
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


class CrestError(ValueError):
    """The upload is not a usable crest image; ``code`` is shown to the user in Spanish by the app."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_crest(raw: bytes) -> bytes:
    """The crest as a square 256 px PNG with transparent margins (aspect ratio kept)."""
    if not raw:
        raise CrestError("CREST_EMPTY", "The file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise CrestError("CREST_TOO_LARGE", "The crest image must be 2 MB or smaller.")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise CrestError("CREST_FORMAT", "Use a PNG, JPG or WebP image.")
            if probe.width * probe.height > MAX_PIXELS:
                raise CrestError("CREST_TOO_LARGE", "The image has too many pixels.")
            probe.verify()                              # structural check, then decode again
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            picture = image.convert("RGBA")
    except CrestError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise CrestError("CREST_FORMAT", "The file is not a valid image.") from error

    picture.thumbnail((CREST_SIZE, CREST_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (CREST_SIZE, CREST_SIZE), (0, 0, 0, 0))
    canvas.paste(picture, ((CREST_SIZE - picture.width) // 2, (CREST_SIZE - picture.height) // 2), picture)
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    data = output.getvalue()
    if len(data) > MAX_STORED_BYTES:                    # a 256 px PNG is far smaller; kept as a guard
        raise CrestError("CREST_TOO_LARGE", "The crest image is too large.")
    return data
