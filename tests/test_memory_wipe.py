"""Conversation erase drops learned memory, not who Mina is."""

import os

import src.hippocampus.hippocampus as hip


def test_wipe_removes_diary_knowledge_relationships_and_rag(tmp_path, monkeypatch):
    kag = tmp_path / "kag"
    knowledge = kag / "KNOWLEDGE"
    knowledge.mkdir(parents=True)
    (kag / "REFLECTION.md").write_text("friday on the couch", encoding="utf-8")
    (kag / "PENDING.md").write_text("follow up", encoding="utf-8")
    (knowledge / "ryan.md").write_text("he is ryan", encoding="utf-8")

    rel = tmp_path / "relationships"
    rel.mkdir()
    (rel / "ryan.md").write_text("bonding: 2", encoding="utf-8")

    rag = tmp_path / "rag"
    rag.mkdir()
    (rag / "chroma.sqlite3").write_bytes(b"not-a-real-db")

    monkeypatch.setattr(hip, "KAG_DIR", str(kag))
    monkeypatch.setattr(hip, "RELATIONSHIP_DIR", str(rel))
    monkeypatch.setattr(hip, "RAG_DIR", str(rag))
    monkeypatch.setattr(hip, "SLIDING_SEQ_FILE", str(tmp_path / "sliding_seq.json"))

    removed = hip.wipe_accumulated_memory()

    assert "kag/REFLECTION.md" in removed
    assert "kag/KNOWLEDGE/ryan.md" in removed
    assert "relationship/ryan.md" in removed
    assert not (kag / "REFLECTION.md").exists()
    assert not (knowledge / "ryan.md").exists()
    assert not (rel / "ryan.md").exists()
    assert not rag.exists()
    assert kag.is_dir()
