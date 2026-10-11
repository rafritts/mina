"""Chat is text only. Image markup is stripped and the photo pathway is gone."""

from __future__ import annotations

from pathlib import Path

from src.application.infra.plain_text import strip_image_markup
from src.application.infra import ui_chat

ROOT = Path(__file__).resolve().parents[1]


def test_strip_image_markup_removes_pictures() -> None:
    raw = (
        "hello\n\n"
        "![photo](/images/keep.png)\n"
        "see /images/also.webp now\n"
        '<img src="/api/generate/x.png" alt="x">\n'
        "still here"
    )
    assert strip_image_markup(raw) == "hello\n\nsee now\n\nstill here"


def test_ui_chat_drops_stored_images(tmp_path, monkeypatch) -> None:
    path = tmp_path / "ui_chat.json"
    monkeypatch.setattr(ui_chat, "UI_CHAT_PATH", path)
    path.write_text(
        """{
  "updatedAt": 1,
  "putRevision": 2,
  "imageAspect": "portrait",
  "imageCount": 3,
  "imageBackend": "mint",
  "messages": [
    {
      "id": "a-1",
      "role": "assistant",
      "content": "look\\n\\n![photo](/images/a.png)",
      "images": ["/images/a.png"],
      "imagePending": true
    }
  ]
}
""",
        encoding="utf-8",
    )
    store = ui_chat.read_store()
    assert "imageAspect" not in store
    assert "imageBackend" not in store
    msg = store["messages"][0]
    assert msg["content"] == "look"
    assert "images" not in msg
    assert "imagePending" not in msg

    ui_chat.append_assistant("next\n\n![x](https://example.com/a.png)")
    saved = path.read_text(encoding="utf-8")
    assert "/images/" not in saved
    assert "imageBackend" not in saved
    assert "https://example.com" not in saved


def test_photo_modules_and_ui_are_gone() -> None:
    for rel in (
        "src/application/infra/comfy.py",
        "src/application/infra/grok_imagine.py",
        "src/application/infra/image_backend.py",
        "src/brain/chat_tools.py",
        "ui/app/components/Lightbox.tsx",
        "ui/app/components/shell/PhotoSettings.tsx",
        "ui/app/lib/image-backend.ts",
        "ui/app/images/[...name]/route.ts",
    ):
        assert not (ROOT / rel).exists(), rel

    server = (ROOT / "src/gateway/server.py").read_text(encoding="utf-8")
    assert "/api/image-backend" not in server
    chat = (ROOT / "ui/app/components/ChatApp.tsx").read_text(encoding="utf-8")
    assert "<img" not in chat
    tools = (ROOT / "ui/app/components/shell/ToolsSheet.tsx").read_text(encoding="utf-8")
    assert "PhotoSettings" not in tools
