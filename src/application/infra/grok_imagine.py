"""
Chat photos via Grok Imagine.

Headless Grok Build: `-p` / `--single` send one prompt and exit
(https://docs.x.ai/build/cli/headless-scripting). Imagine is the
image_gen tool inside that run, not a second image API.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from src.application.infra import comfy
from src.application.infra.client import (
    _child_env,
    _discard_oneshot_session,
    grok_bin,
    oneshot_grok_home,
)
from src.application.infra.log import log

_ASPECT_RATIO = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "2:3",
}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
# Absolute paths, plus the session-relative images/1.jpg form Imagine prints.
_IMAGE_PATH = re.compile(
    r"(?P<p>(?:/[^\s\"'`<>]+|images/[A-Za-z0-9._/-]+)\.(?:png|jpe?g|webp))",
    re.IGNORECASE,
)


def _aspect_ratio(aspect: str) -> str:
    return _ASPECT_RATIO.get(aspect, "1:1")


def _imagine_prompt(full_prompt: str, aspect: str) -> str:
    ratio = _aspect_ratio(aspect)
    return (
        "Call the image_gen tool exactly once. "
        f"Set aspect_ratio to {ratio}. "
        "Use the prompt below as the image_gen prompt, unchanged. "
        "Do not search, do not edit files, and do not generate a second image.\n\n"
        f"{full_prompt}"
    )


def _timeout_sec() -> float:
    raw = os.getenv("MINA_GROK_IMAGE_TIMEOUT_MS", os.getenv("MINA_GROK_TIMEOUT_MS", "180000"))
    try:
        ms = int(raw)
    except ValueError:
        ms = 180_000
    return max(5.0, ms / 1000.0)


def _paths_in_text(text: str, cwd: Path) -> list[Path]:
    found: list[Path] = []
    for match in _IMAGE_PATH.finditer(text or ""):
        raw = match.group("p")
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        found.append(path)
    return found


def _walk_new_images(root: Path, since: float) -> list[Path]:
    if not root.exists():
        return []
    found: list[Path] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).resolve().relative_to(root)
        if len(rel.parts) > 5:
            dirnames.clear()
            continue
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in _IMAGE_EXT:
                continue
            try:
                if path.stat().st_mtime < since - 1:
                    continue
            except OSError:
                continue
            found.append(path)
    return found


def _existing(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        if resolved.suffix.lower() not in _IMAGE_EXT:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _choose_image(stdout: str, stderr: str, cwd: Path, grok_home: Path, since: float) -> Path:
    mentioned = _existing(_paths_in_text(stdout, cwd) + _paths_in_text(stderr, cwd))
    if mentioned:
        return mentioned[-1]
    scanned = _existing(_walk_new_images(cwd, since) + _walk_new_images(grok_home, since))
    if not scanned:
        tail = (stderr or stdout).strip()[-400:]
        raise RuntimeError(
            "grok Imagine did not write an image"
            + (f": {tail}" if tail else "")
        )
    return max(scanned, key=lambda p: p.stat().st_mtime)


def _session_id(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    sid = payload.get("sessionId") or payload.get("session_id")
    return sid if isinstance(sid, str) else None


def generate_with_grok(
    prompt: str,
    *,
    aspect: str = "square",
) -> dict:
    """
    Run `grok -p` (Imagine / image_gen) and copy the image into run/chat-images/.

    Returns {url, path} where url is /images/{name}.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("empty prompt")

    cwd = Path(tempfile.mkdtemp(prefix="mina-imagine-"))
    grok_home = oneshot_grok_home()
    started = time.time()
    instruction = _imagine_prompt(prompt, aspect)
    args = [
        grok_bin(),
        "--no-auto-update",
        "-p",
        instruction,
        "--output-format",
        "json",
        "--always-approve",
        "--permission-mode",
        "bypassPermissions",
        "--max-turns",
        "4",
        "--no-subagents",
        "--no-memory",
        "--disable-web-search",
        "--tools",
        "image_gen",
        "--cwd",
        str(cwd),
    ]
    log("GROK_IMAGINE", f"spawn aspect={_aspect_ratio(aspect)}")
    try:
        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd),
                env=_child_env(),
                capture_output=True,
                text=True,
                timeout=_timeout_sec(),
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"grok binary not found ({grok_bin()})") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"grok timed out after {_timeout_sec():.0f}s") from e

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        try:
            image = _choose_image(stdout, stderr, cwd, grok_home, started)
        except RuntimeError:
            if proc.returncode != 0:
                tail = (stderr.strip() or stdout.strip())[-500:]
                raise RuntimeError(
                    f"grok exited {proc.returncode}" + (f": {tail}" if tail else "")
                ) from None
            raise

        ext = image.suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        name = f"grok-{uuid.uuid4().hex[:12]}{ext}"
        comfy.CHAT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        dest = comfy.CHAT_IMAGES_DIR / name
        shutil.copyfile(image, dest)
        _discard_oneshot_session(_session_id(stdout), grok_home)
        url = f"/images/{name}"
        log("GROK_IMAGINE", f"saved → {url} ({dest.stat().st_size} bytes)")
        return {"url": url, "path": str(dest)}
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
