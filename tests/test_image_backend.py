"""RES-126 — chat photo source: mint, grok, or off."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from src.application.infra import comfy, image_backend
from src.application.infra import ui_chat
from src.brain import chat_tools
from src.gateway.server import app

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui" / "app"


def test_missing_setting_defaults_to_mint(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_chat, "UI_CHAT_PATH", tmp_path / "ui_chat.json")
    assert image_backend.read_image_backend() == "mint"
    assert chat_tools.normalize_image_backend(None) == "mint"
    assert chat_tools.normalize_image_backend("nope") == "mint"


def test_set_backend_keeps_transcript_aspect_and_count(tmp_path, monkeypatch):
    path = tmp_path / "ui_chat.json"
    monkeypatch.setattr(ui_chat, "UI_CHAT_PATH", path)
    path.write_text(
        json.dumps(
            {
                "updatedAt": 1,
                "putRevision": 3,
                "messages": [{"id": "u-1", "role": "user", "content": "keep me"}],
                "imageAspect": "portrait",
                "imageCount": "auto",
            }
        ),
        encoding="utf-8",
    )

    ui_chat.set_image_backend("off")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["imageBackend"] == "off"
    assert saved["messages"][0]["content"] == "keep me"
    assert saved["imageAspect"] == "portrait"
    assert saved["imageCount"] == "auto"

    ui_chat.set_image_backend("grok")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["imageBackend"] == "grok"
    assert saved["messages"] == [{"id": "u-1", "role": "user", "content": "keep me"}]
    assert saved["imageAspect"] == "portrait"
    assert saved["imageCount"] == "auto"
    assert image_backend.read_image_backend() == "grok"


def test_off_still_leaves_count_cap_intact():
    assert chat_tools.photos_allowed(3, "off") is False
    assert chat_tools.photos_allowed(0, "grok") is False
    assert chat_tools.photos_allowed(3, "grok") is True
    assert chat_tools.photos_allowed("auto", "mint") is True
    assert chat_tools.max_photos(4) == 4
    text = chat_tools.photo_turn_context(4, "portrait", "off")
    assert "image generation is off" in text
    assert "Send exactly 4" not in text
    # Count copy is unchanged when a backend is selected.
    assert "Send exactly 4" in chat_tools.photo_turn_context(4, "portrait", "grok")


def test_health_payload_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_chat, "UI_CHAT_PATH", tmp_path / "ui_chat.json")
    ui_chat.set_image_backend("grok")
    monkeypatch.setattr(image_backend, "probe_mint", lambda timeout=1.5: False)
    monkeypatch.setenv("MINT_COMFY_URL", "http://restless-mint:8188")

    body = image_backend.image_backend_status()

    assert set(body) == {"backend", "mint"}
    assert set(body["mint"]) == {"up", "url"}
    assert body["backend"] == "grok"
    assert body["mint"]["up"] is False
    assert body["mint"]["url"] == "http://restless-mint:8188"


def test_probe_mint_down_on_connection_refused(monkeypatch):
    monkeypatch.setenv("MINT_COMFY_URL", "http://127.0.0.1:1")
    assert image_backend.probe_mint(timeout=0.4) is False


def test_get_image_backend_route(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_chat, "UI_CHAT_PATH", tmp_path / "ui_chat.json")
    ui_chat.set_image_backend("off")
    monkeypatch.setattr(image_backend, "probe_mint", lambda timeout=1.5: True)
    monkeypatch.setenv("MINT_COMFY_URL", "http://restless-mint:8188")

    res = TestClient(app).get("/api/image-backend")

    assert res.status_code == 200
    body = res.json()
    assert body["backend"] == "off"
    assert body["mint"] == {"up": True, "url": "http://restless-mint:8188"}


def test_patch_rejects_mint_when_down_without_wiping_prefs(tmp_path, monkeypatch):
    path = tmp_path / "ui_chat.json"
    monkeypatch.setattr(ui_chat, "UI_CHAT_PATH", path)
    path.write_text(
        json.dumps(
            {
                "updatedAt": 1,
                "putRevision": 1,
                "messages": [{"id": "a-1", "role": "assistant", "content": "hi"}],
                "imageAspect": "landscape",
                "imageCount": 2,
                "imageBackend": "grok",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(image_backend, "probe_mint", lambda timeout=1.5: False)

    res = TestClient(app).patch("/api/image-backend", json={"backend": "mint"})

    assert res.status_code == 409
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["imageBackend"] == "grok"
    assert saved["imageAspect"] == "landscape"
    assert saved["imageCount"] == 2
    assert saved["messages"][0]["content"] == "hi"


def test_off_does_not_call_comfy_or_grok(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("backend was called")

    monkeypatch.setattr(chat_tools, "generate_and_save", boom)
    monkeypatch.setattr(chat_tools, "generate_with_grok", boom)
    monkeypatch.setattr(chat_tools, "probe_mint", boom)

    out = chat_tools.handle_send_photo(
        {"prompt": "sitting on the couch, jeans and a t-shirt"},
        image_aspect="square",
        image_backend="off",
    )

    assert out == "[send_photo failed: image generation is off]"


def test_grok_path_does_not_call_comfy(tmp_path, monkeypatch):
    monkeypatch.setattr(comfy, "CHAT_IMAGES_DIR", tmp_path)
    monkeypatch.setattr(
        chat_tools,
        "generate_and_save",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("comfy called")),
    )
    monkeypatch.setattr(chat_tools, "probe_mint", lambda *_a, **_k: False)

    def fake_run(args, **kwargs):
        assert "-p" in args
        assert "--single" not in args
        prompt = args[args.index("-p") + 1]
        assert "image_gen" in prompt
        assert "jeans" in prompt
        cwd = Path(kwargs["cwd"])
        img = cwd / "shot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps({"text": str(img)}),
            stderr="",
        )

    monkeypatch.setattr(
        "src.application.infra.grok_imagine.subprocess.run",
        fake_run,
    )

    out = chat_tools.handle_send_photo(
        {"prompt": "sitting on the couch, jeans and a t-shirt", "caption": "hey"},
        image_aspect="landscape",
        image_backend="grok",
    )

    assert out.startswith("hey\n\n![hey](/images/grok-")
    assert out.endswith(".png)")
    saved = list(tmp_path.glob("grok-*.png"))
    assert len(saved) == 1
    assert saved[0].read_bytes().startswith(b"\x89PNG")


def test_mint_down_fails_without_calling_comfy(monkeypatch):
    monkeypatch.setattr(chat_tools, "probe_mint", lambda: False)
    monkeypatch.setattr(chat_tools, "mint_comfy_url", lambda: "http://restless-mint:8188")
    monkeypatch.setattr(
        chat_tools,
        "generate_and_save",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("comfy called")),
    )
    monkeypatch.setattr(
        chat_tools,
        "generate_with_grok",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("grok called")),
    )

    out = chat_tools.handle_send_photo(
        {"prompt": "close selfie, soft smile, jeans"},
        image_backend="mint",
    )

    assert out == "[send_photo failed: Mint is down (http://restless-mint:8188)]"


def test_mint_up_calls_comfy_not_grok(monkeypatch):
    monkeypatch.setattr(chat_tools, "probe_mint", lambda: True)
    monkeypatch.setattr(
        chat_tools,
        "generate_with_grok",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("grok called")),
    )

    def fake_comfy(prompt, **kwargs):
        assert "jeans" in prompt
        assert kwargs["aspect"] == "portrait"
        return {"url": "/images/job.png", "path": "/tmp/job.png"}

    monkeypatch.setattr(chat_tools, "generate_and_save", fake_comfy)

    out = chat_tools.handle_send_photo(
        {"prompt": "standing by the window, jeans and a shirt"},
        image_aspect="portrait",
        image_backend="mint",
    )

    assert out == "![photo](/images/job.png)"


def test_tools_sheet_offers_mint_grok_and_no_images():
    tools = (UI / "components/shell/ToolsSheet.tsx").read_text(encoding="utf-8")
    photos = (UI / "components/shell/PhotoSettings.tsx").read_text(encoding="utf-8")
    options = (UI / "lib/image-backend.ts").read_text(encoding="utf-8")
    assert "PhotoSettings" in tools
    assert "ImageCountSelector" in photos
    assert "AspectRatioSlider" in photos
    assert "IMAGE_BACKEND_OPTIONS" in photos
    assert "{ value: 'off', label: 'No images' }" in options
    assert "{ value: 'mint', label: 'Mint' }" in options
    assert "{ value: 'grok', label: 'Grok' }" in options
    assert "/api/image-backend" in photos
    assert "Mint down" in photos
    assert "disabled={disabled}" in photos
    # Composer controls stay.
    chat = (UI / "components/ChatApp.tsx").read_text(encoding="utf-8")
    assert "ImageCountSelector" in chat
    assert "AspectRatioSlider" in chat
    assert "image_backend:" in chat
