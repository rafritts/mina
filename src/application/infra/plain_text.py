"""Strip image markup so chat stays text."""

from __future__ import annotations

import re

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_BARE_HOST_IMAGE = re.compile(r"(?<![\w(/])(?:/images/|/api/generate/)\S+")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_BLANK_RUN = re.compile(r"\n(?:[ \t]*\n){2,}")


def strip_image_markup(text: str) -> str:
    """Remove markdown images, HTML images, and host image paths."""
    if not isinstance(text, str) or not text:
        return ""
    out = _HTML_IMAGE.sub("", text)
    out = _MD_IMAGE.sub("", out)
    out = _BARE_HOST_IMAGE.sub("", out)
    out = _MULTI_SPACE.sub(" ", out)
    out = _BLANK_RUN.sub("\n\n", out)
    return out.strip()
