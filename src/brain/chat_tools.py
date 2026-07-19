"""
Chat-turn tools (photos via comfy-fe). Separate from FREETIME tools.
"""
from __future__ import annotations

import json

from src.application.infra.comfy import build_photo_prompt, generate_and_save
from src.application.infra.log import log

CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_photo",
            "description": (
                "Send a photo of yourself (selfie or scene shot) to the chat. "
                "Use when a picture fits the moment — when they ask, when you're "
                "showing something, or when a photo is more honest than text. "
                "Do not spam photos. Respect the photo count guidance in the prompt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "What the photo shows: pose, expression, clothing, setting, "
                            "framing. Do not restate your full face description — the host "
                            "adds your fixed appearance. Concrete and visual."
                        ),
                    },
                    "caption": {
                        "type": "string",
                        "description": "Short optional caption shown with the photo.",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]


def max_photos(image_count) -> int:
    """UI image_count → hard cap on send_photo this turn."""
    if image_count == 0 or image_count == "0":
        return 0
    if isinstance(image_count, int) and 1 <= image_count <= 5:
        return image_count
    if isinstance(image_count, str) and image_count.isdigit():
        n = int(image_count)
        if 1 <= n <= 5:
            return n
    # auto / missing
    return 1


def photo_turn_context(image_count, image_aspect: str) -> str:
    """Injected into system prompt for this turn."""
    aspect = image_aspect if image_aspect in ("landscape", "square", "portrait") else "square"
    aspect_hint = {
        "landscape": "16:9 widescreen",
        "square": "1:1 square",
        "portrait": "2:3 portrait",
    }[aspect]

    if image_count == 0 or image_count == "0":
        return (
            "[Photo settings]\n"
            "No photos this reply — text only. Do not call send_photo."
        )

    if isinstance(image_count, int) or (isinstance(image_count, str) and image_count.isdigit()):
        n = int(image_count)
        count_line = f"Send exactly {n} photo{'s' if n != 1 else ''} this reply (call send_photo {n} time{'s' if n != 1 else ''})."
    else:
        count_line = (
            "Photos: auto — at most one photo unless they clearly ask for more. "
            "Skip photos when a text reply is enough."
        )

    return (
        f"[Photo settings]\n"
        f"{count_line}\n"
        f"Preferred aspect: {aspect_hint}.\n"
        f"When you send a photo, call send_photo with a concrete scene prompt "
        f"(expression, clothes, place, framing). Your fixed look is applied by the host."
    )


def handle_send_photo(args: dict, *, image_aspect: str = "square") -> str:
    """Generate via comfy and return markdown the UI can render."""
    scene = (args.get("prompt") or "").strip()
    caption = (args.get("caption") or "").strip()
    if not scene:
        return "[send_photo: empty prompt]"

    full_prompt = build_photo_prompt(scene)
    try:
        result = generate_and_save(
            full_prompt,
            aspect=image_aspect,
            filename_prefix="mina",
        )
    except Exception as e:
        log("CHAT_TOOL/PHOTO/ERR", str(e))
        return f"[send_photo failed: {e}]"

    alt = caption.replace("]", "").replace("[", "") or "photo"
    if caption:
        return f"{caption}\n\n![{alt}]({result['url']})"
    return f"![{alt}]({result['url']})"


def call_chat_tool(name: str, args: dict, *, image_aspect: str = "square") -> str:
    if name == "send_photo":
        return handle_send_photo(args, image_aspect=image_aspect)
    return f"[Unknown chat tool: {name}]"


def parse_tool_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
