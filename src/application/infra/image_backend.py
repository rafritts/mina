"""
Chat photo source: mint (Comfy on restless-mint), grok (Imagine), or off.

Mint reachability is an HTTP GET from this process to MINT_COMFY_URL
(default http://restless-mint:8188). No SSH. The Krea frontend
(COMFY_FE_URL, default http://127.0.0.1:8886) is a separate hop and is
not what "Mint up" means.
"""
from __future__ import annotations

import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_IMAGE_BACKEND = "mint"
IMAGE_BACKENDS = ("mint", "grok", "off")
_DEFAULT_MINT_URL = "http://restless-mint:8188"


def mint_comfy_url() -> str:
    raw = (os.getenv("MINT_COMFY_URL") or _DEFAULT_MINT_URL).strip()
    return raw.rstrip("/") or _DEFAULT_MINT_URL


def parse_image_backend(raw) -> str | None:
    if isinstance(raw, str) and raw.strip().lower() in IMAGE_BACKENDS:
        return raw.strip().lower()
    return None


def read_image_backend() -> str:
    """Saved setting, or mint when the field is absent."""
    from src.application.infra.ui_chat import image_backend_value, read_store

    return image_backend_value(read_store().get("imageBackend")) or DEFAULT_IMAGE_BACKEND


def probe_mint(timeout: float = 1.5) -> bool:
    """
    True when Mint's ComfyUI answers HTTP. Connection failure is down.

    An HTTP error status still counts as up: the host answered.
    """
    url = mint_comfy_url() + "/"
    req = Request(
        url,
        headers={"Accept": "*/*", "User-Agent": "mina-image-backend"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            code = getattr(res, "status", None) or res.getcode()
            return 100 <= int(code) < 600
    except HTTPError as e:
        return 100 <= int(e.code) < 600
    except (URLError, TimeoutError, OSError, ValueError):
        return False


def image_backend_status() -> dict:
    """GET /api/image-backend body."""
    return {
        "backend": read_image_backend(),
        "mint": {
            "up": probe_mint(),
            "url": mint_comfy_url(),
        },
    }
