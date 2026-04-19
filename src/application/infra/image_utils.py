"""Shared image normalisation utility used by both the Discord gateway and cortex."""
import base64
import io

from PIL import Image

_IMAGE_MAX_EDGE  = 1024    # px — resize before encoding
_IMAGE_MAX_BYTES = 300_000  # 300 KB target


def normalise_image(data: bytes, mime: str = "image/png") -> tuple[str, str]:
    """
    Resize to fit within _IMAGE_MAX_EDGE, re-encode as JPEG, and aggressively
    reduce quality + dimensions until under _IMAGE_MAX_BYTES.
    Returns (base64_string, mime_type).
    """
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size

    max_edge = _IMAGE_MAX_EDGE
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    compressed = b""
    for quality in (80, 70, 60, 50, 40, 30, 20, 10, 5):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= _IMAGE_MAX_BYTES:
            return base64.b64encode(compressed).decode("utf-8"), "image/jpeg"

    # Quality reduction alone wasn't enough — halve dimensions and retry
    w2, h2 = img.size
    img = img.resize((w2 // 2, h2 // 2), Image.LANCZOS)
    for quality in (60, 40, 20):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= _IMAGE_MAX_BYTES:
            break

    return base64.b64encode(compressed).decode("utf-8"), "image/jpeg"
