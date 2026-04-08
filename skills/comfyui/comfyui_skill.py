"""
ComfyUI image generation skill.

Pure async generator — queues a job, polls until complete, saves the result
to disk, and returns the path. No Discord logic. Adapted from raika.

Usage (CLI):
    python comfyui_skill.py --prompt "1girl, solo, ..." --dimensions "832x1216" \
        --filename "mina_selfie"
"""
import argparse
import asyncio
import io
import json
import logging
import os
import random
import shutil
import tempfile
import uuid

import aiohttp
from PIL import Image

log = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "../.."))
_TEMPLATE_UPSCALE = os.path.join(_SCRIPT_DIR, "RestlessSimpleAPI_template.json")
_TEMPLATE_NO_UPSCALE = os.path.join(_SCRIPT_DIR, "RestlessSimpleAPI_NoUpscale_template.json")
_IMAGES_DIR = os.path.join(_PROJECT_ROOT, "workspace", "images")

COMFYUI_HOST = os.getenv("COMFYUI_HOST", "localhost")
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"

# Lazy-loaded — only imported if restricted detection is needed
_CONTENT_DETECTOR = None


def _allow_restricted() -> bool:
    """Read from config.json. Defaults to False."""
    config_path = os.path.join(_PROJECT_ROOT, "config.json")
    try:
        with open(config_path) as f:
            return json.load(f).get("allow_image_generations", False)
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def _is_blocked_restricted(image_bytes: bytes) -> bool:
    if _allow_restricted():
        return False

    global _CONTENT_DETECTOR
    try:
        from content_image_detector import ContentDetector
        if _CONTENT_DETECTOR is None:
            _CONTENT_DETECTOR = ContentDetector()
    except ImportError:
        log.warning("content_image_detector not installed — skipping restricted check")
        return False

    with Image.open(io.BytesIO(image_bytes)) as img:
        rgb = img.convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            rgb.save(tmp, format="JPEG")

    try:
        prediction = _CONTENT_DETECTOR.detect(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if isinstance(prediction, dict):
        nested = next((v for v in prediction.values() if isinstance(v, dict)), None)
        scores = nested if nested else prediction
        restricted_keys = ("restricted", "adult media", "adult_media", "explicit", "intimate")
        score = max(float(scores.get(k, 0.0)) for k in restricted_keys)
        return score >= 0.75
    return False


async def _check_reachable(session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get(f"{COMFYUI_URL}/queue", timeout=aiohttp.ClientTimeout(total=3)) as resp:
            return resp.status == 200
    except Exception:
        return False


async def generate_image(
    prompt: str,
    dimensions: str = "832x1216",
    filename: str = "mina",
    negative_prompt: str | None = None,
    seed: int | None = None,
    uid: str | None = None,
    workflow: str = "upscale",
) -> str:
    """
    Generate an image via ComfyUI and save to disk.

    Returns the absolute path to the saved PNG, or "" if blocked/failed.

    Args:
        prompt: Positive prompt (Danbooru-style tags)
        dimensions: "WIDTHxHEIGHT" e.g. "832x1216"
        filename: Base filename (no extension)
        negative_prompt: Negative prompt. Defaults to a sensible set.
        seed: None or 0 = random
        uid: Optional suffix for filename uniqueness
        workflow: "upscale" (~60s, higher quality) or "no_upscale" (~20s, faster)
    """
    if negative_prompt is None:
        negative_prompt = "blurry, ugly, deformed, low quality, watermark, text, signature"

    template_path = _TEMPLATE_NO_UPSCALE if workflow == "no_upscale" else _TEMPLATE_UPSCALE

    try:
        width, height = map(int, dimensions.split("x"))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid dimensions {dimensions!r} — expected WIDTHxHEIGHT e.g. '832x1216'")

    temp_path = os.path.join(
        os.path.dirname(template_path),
        f"temp_workflow_{random.randint(0, 1_000_000)}.json",
    )
    shutil.copy(template_path, temp_path)

    save_node_id: str | None = None
    prompt_id: str | None = None

    try:
        with open(temp_path) as f:
            wf = json.load(f)

        save_node_id = next(
            (k for k, v in wf.items() if v.get("class_type") == "SaveImage"), None
        )
        if save_node_id is None:
            raise RuntimeError("No SaveImage node found in workflow.")

        seed_value = seed if seed else random.randint(0, 2**32 - 1)

        for node in wf.values():
            ct = node.get("class_type", "")
            inputs = node.get("inputs", {})
            title = node.get("_meta", {}).get("title", "")
            if ct == "EmptyLatentImage":
                inputs["width"], inputs["height"] = width, height
            elif ct == "UltimateSDUpscale":
                inputs["seed"] = seed_value
                inputs["tile_width"], inputs["tile_height"] = width * 2, height * 2
            elif ct == "KSampler" or "seed" in inputs:
                inputs["seed"] = seed_value
            elif title == "CLIP Text Encode (Prompt)":
                inputs["text"] = prompt
            elif title == "CLIP Text Encode (Negative)":
                inputs["text"] = negative_prompt
            elif ct == "SaveImage":
                inputs["filename_prefix"] = filename

        with open(temp_path, "w") as f:
            json.dump(wf, f)

        connector = aiohttp.TCPConnector(force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            if not await _check_reachable(session):
                raise RuntimeError(f"ComfyUI unreachable at {COMFYUI_URL}")

            async with session.post(f"{COMFYUI_URL}/prompt", json={"prompt": wf}) as resp:
                result = await resp.json()

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if "prompt_id" not in result:
        raise RuntimeError(f"ComfyUI rejected prompt: {result}")

    prompt_id = result["prompt_id"]

    # Poll until complete
    connector = aiohttp.TCPConnector(force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            async with session.get(f"{COMFYUI_URL}/queue") as resp:
                queue = await resp.json()
            running = [item[1] for item in queue.get("queue_running", [])]
            pending = [item[1] for item in queue.get("queue_pending", [])]
            if prompt_id not in running and prompt_id not in pending:
                break
            await asyncio.sleep(1)

        while True:
            async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as resp:
                if resp.status == 200:
                    history = await resp.json()
                    if prompt_id in history and "outputs" in history[prompt_id]:
                        break
            await asyncio.sleep(1)

        outputs = history[prompt_id]["outputs"]
        if save_node_id not in outputs or not outputs[save_node_id].get("images"):
            raise RuntimeError("No images in ComfyUI output.")

        image_info = outputs[save_node_id]["images"][0]
        params = {"filename": image_info["filename"], "type": "output"}
        if image_info.get("subfolder"):
            params["subfolder"] = image_info["subfolder"]

        async with session.get(f"{COMFYUI_URL}/view", params=params) as resp:
            img_data = await resp.read()

    try:
        blocked = _is_blocked_restricted(img_data)
    except Exception as e:
        log.warning("restricted detector error, allowing image: %s", e)
        blocked = False

    if blocked:
        log.info("Image blocked by restricted detector.")
        return ""

    suffix = uid or uuid.uuid4().hex[:4]
    os.makedirs(_IMAGES_DIR, exist_ok=True)
    out_path = os.path.join(_IMAGES_DIR, f"{filename}_{suffix}.png")
    with open(out_path, "wb") as f:
        f.write(img_data)

    log.info("Image saved: %s", out_path)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--dimensions", default="832x1216")
    parser.add_argument("--filename", default="mina")
    parser.add_argument("--negative-prompt", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--workflow", default="upscale", choices=["upscale", "no_upscale"])
    args = parser.parse_args()

    path = asyncio.run(generate_image(
        args.prompt,
        args.dimensions,
        args.filename,
        args.negative_prompt,
        args.seed,
        workflow=args.workflow,
    ))

    if path:
        print(f"Saved: {path}")
    else:
        import sys
        print("Generation blocked or failed.")
        sys.exit(1)
