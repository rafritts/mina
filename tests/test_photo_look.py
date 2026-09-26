"""Photo look follows the scene: clothed block, or the when-nude block."""

import src.application.infra.comfy as comfy

_SECTION = """
### Prose — clothed
CLOTHED LOOK
### When nude
NUDE LOOK
### Image habits
- habits
"""


def test_dressed_brief_uses_clothed_look(monkeypatch):
    monkeypatch.setattr(comfy, "_appearance_section", lambda: _SECTION)
    monkeypatch.setattr(comfy, "_mina_clothing_undressed", lambda: False)
    prompt = comfy.build_photo_prompt("Close selfie on the couch, shorts and a tank top")
    assert "CLOTHED LOOK" in prompt
    assert "NUDE LOOK" not in prompt


def test_undressed_brief_uses_nude_look(monkeypatch):
    monkeypatch.setattr(comfy, "_appearance_section", lambda: _SECTION)
    monkeypatch.setattr(comfy, "_mina_clothing_undressed", lambda: False)
    prompt = comfy.build_photo_prompt("Lying in bed, nude, looking at the lens")
    assert "NUDE LOOK" in prompt
    assert "CLOTHED LOOK" not in prompt


def test_stored_scene_undressed_uses_nude_look(monkeypatch):
    monkeypatch.setattr(comfy, "_appearance_section", lambda: _SECTION)
    monkeypatch.setattr(comfy, "_mina_clothing_undressed", lambda: True)
    prompt = comfy.build_photo_prompt("Close selfie in bed, soft smile")
    assert "NUDE LOOK" in prompt
    assert "CLOTHED LOOK" not in prompt
