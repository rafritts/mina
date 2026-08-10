"""
Comfy-restless-frontend client (Krea workflow).

Same host path Kairu uses: POST /api/generate → poll → download image.
Saves durable files under run/chat-images/ served by the Next UI at /images/*.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.application.infra.log import log
from src.config.config import RUN_DIR

COMFY_FE_URL = os.getenv("COMFY_FE_URL", "http://127.0.0.1:8886").rstrip("/")
CHAT_IMAGES_DIR = Path(RUN_DIR) / "chat-images"

ASPECT_KREA = {
    "landscape": "16:9 (Widescreen)",
    "square": "1:1 (Square)",
    "portrait": "2:3 (Portrait Photo)",
}


def krea_aspect(aspect: str | None) -> str:
    if not aspect:
        return ASPECT_KREA["square"]
    if aspect in ASPECT_KREA:
        return ASPECT_KREA[aspect]
    # Already a krea label
    if "(" in aspect:
        return aspect
    return ASPECT_KREA.get(aspect, ASPECT_KREA["square"])


def _http_json(method: str, path: str, body: dict | None = None, timeout: float = 60.0) -> dict:
    import json

    url = f"{COMFY_FE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as res:
        raw = res.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _http_bytes(path: str, timeout: float = 120.0) -> tuple[bytes, str | None]:
    url = f"{COMFY_FE_URL}{path}"
    req = Request(url, headers={"Accept": "image/*,*/*"}, method="GET")
    with urlopen(req, timeout=timeout) as res:
        ct = res.headers.get("Content-Type")
        return res.read(), ct


def _ext_from_bytes(buf: bytes, content_type: str | None) -> str:
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base in ("image/jpeg", "image/jpg"):
            return ".jpg"
        if base == "image/png":
            return ".png"
        if base == "image/webp":
            return ".webp"
    if len(buf) >= 3 and buf[0] == 0xFF and buf[1] == 0xD8 and buf[2] == 0xFF:
        return ".jpg"
    if len(buf) >= 8 and buf[:4] == b"\x89PNG":
        return ".png"
    if len(buf) >= 12 and buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def generate_and_save(
    prompt: str,
    *,
    aspect: str = "square",
    megapixels: float = 2.0,
    steps: int = 8,
    seed: int | None = None,
    filename_prefix: str = "mina",
    poll_ms: float = 1.5,
    max_wait_s: float = 15 * 60,
) -> dict:
    """
    Queue a Krea job, wait until done, persist under run/chat-images/.

    Returns: {url, job_id, seed, path} where url is /images/{name} for the UI.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("empty prompt")

    body = {
        "workflow": "krea",
        "prompt": prompt,
        "aspect_ratio": krea_aspect(aspect),
        "megapixels": megapixels,
        "steps": steps,
        "seed": seed,
        "filename_prefix": filename_prefix,
    }

    try:
        started = _http_json("POST", "/api/generate", body)
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"comfy-fe unreachable ({COMFY_FE_URL}): {e}") from e

    job_id = started.get("job_id")
    if not job_id:
        raise RuntimeError(f"comfy-fe missing job_id: {started}")

    log("COMFY", f"queued job={job_id} aspect={body['aspect_ratio']}")

    deadline = time.time() + max_wait_s
    last_status = started.get("status", "queued")
    while time.time() < deadline:
        time.sleep(poll_ms)
        try:
            job = _http_json("GET", f"/api/generate/{job_id}", timeout=30.0)
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            log("COMFY", f"poll error job={job_id}: {e}")
            continue
        last_status = job.get("status", last_status)
        if last_status == "done":
            buf, ct = _http_bytes(f"/api/generate/{job_id}/image")
            ext = _ext_from_bytes(buf, ct)
            CHAT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            # Prefer comfy job id for stable names; fall back to uuid.
            name = f"{job_id}{ext}"
            path = CHAT_IMAGES_DIR / name
            path.write_bytes(buf)
            url = f"/images/{name}"
            log("COMFY", f"saved job={job_id} → {url} ({len(buf)} bytes)")
            return {
                "url": url,
                "job_id": job_id,
                "seed": job.get("seed", started.get("seed")),
                "path": str(path),
            }
        if last_status == "error":
            raise RuntimeError(job.get("error") or f"comfy job {job_id} failed")

    raise TimeoutError(f"comfy job {job_id} timed out (last={last_status})")


# Same quality anchor Kairu appends to every Krea2 prompt.
KREA_QUALITY_SUFFIX = "amateur photo, 8K UHD photograph, shot on Canon EOS R5"

_DEFAULT_LOOK = (
    "A young woman in her mid-twenties with dark brown hair worn down or "
    "loosely tied, warm brown eyes, light olive skin, soft oval face. "
    "Average height. Simple casual clothes — jeans and a plain shirt or soft layers."
)


def _appearance_section() -> str | None:
    """Krea look blocks: prefer CUSTOMIZATION.md, then identity/MINA.md."""
    from src.config.config import IDENTITY_DIR, REPO_ROOT

    candidates = (
        Path(REPO_ROOT) / "CUSTOMIZATION.md",
        Path(IDENTITY_DIR) / "CUSTOMIZATION.md",
        Path(IDENTITY_DIR) / "MINA.md",
    )
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for h2 in ("## Appearance (Krea)", "## Appearance"):
            if h2 in text:
                after = text.split(h2, 1)[1]
                return after.split("\n## ", 1)[0]
    return None


def _subsection(section: str, *headings: str) -> str | None:
    for heading in headings:
        if heading in section:
            block = section.split(heading, 1)[1]
            block = block.split("\n### ", 1)[0].strip()
            if block:
                return block
    return None


def mina_look_block() -> str:
    """
    Fixed appearance prose for Krea2 prompts (clothed only).

    Third-person visual anchors from CUSTOMIZATION.md (preferred) or
    identity/MINA.md.
    """
    section = _appearance_section()
    if section:
        block = _subsection(
            section,
            "### Prose — clothed",
            "### Photo look (Krea)",
            "### Photo look",
            "### Krea",
        )
        if block:
            return block
    return _DEFAULT_LOOK


def build_photo_prompt(scene_prompt: str) -> str:
    """
    Assemble a Krea2 prompt:

      1. Scene / framing / pose (natural prose from the model)
      2. Fixed clothed appearance prose
      3. Quality suffix

    Krea has no negation — do not put "no X" / "without Y" in prompts.
    Unwanted details are handled by omission; photoreal is anchored by the
    quality suffix.
    """
    scene = (scene_prompt or "").strip()
    if not scene:
        scene = "Close selfie, looking into the lens, soft natural expression."
    look = mina_look_block()
    return f"{scene}\n\n{look}\n\n{KREA_QUALITY_SUFFIX}"
