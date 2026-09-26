"""Chat photos are removed once the transcript no longer cites them."""

from src.application.infra.comfy import gc_chat_images, referenced_image_names


def test_referenced_names_from_markdown_and_list():
    names = referenced_image_names([
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "here\n\n![photo](/images/keep.png)",
            "images": ["/images/also.webp", "https://evil.example/x.png"],
        },
    ])
    assert names == {"keep.png", "also.webp"}


def test_gc_deletes_only_unreferenced(tmp_path, monkeypatch):
    import src.application.infra.comfy as comfy

    monkeypatch.setattr(comfy, "CHAT_IMAGES_DIR", tmp_path)
    (tmp_path / "keep.png").write_bytes(b"keep")
    (tmp_path / "drop.jpg").write_bytes(b"drop")
    (tmp_path / "subdir").mkdir()

    removed = gc_chat_images({"keep.png"})

    assert removed == ["drop.jpg"]
    assert (tmp_path / "keep.png").is_file()
    assert not (tmp_path / "drop.jpg").exists()
    assert (tmp_path / "subdir").is_dir()


def test_gc_clears_directory_when_transcript_is_empty(tmp_path, monkeypatch):
    import src.application.infra.comfy as comfy

    monkeypatch.setattr(comfy, "CHAT_IMAGES_DIR", tmp_path)
    (tmp_path / "a.png").write_bytes(b"a")
    (tmp_path / "b.png").write_bytes(b"b")

    removed = set(gc_chat_images(set()))

    assert removed == {"a.png", "b.png"}
    assert list(tmp_path.iterdir()) == []
