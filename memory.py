"""
Memory layer — KAG (file-based knowledge) and RAG (ChromaDB episodic experiences).

Identity files (MINA.md, APPEARANCE.md) live in identity/ — permanent, never wiped.
KAG files live in memory/kag/ — accumulated knowledge, wiped on reset.
RAG embeddings live in memory/rag/ — episodic memory, wiped on reset.
"""
import os
import time
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_IDENTITY_DIR = os.path.join(_PROJECT_ROOT, "identity")
_KAG_DIR = os.path.join(_PROJECT_ROOT, "memory", "kag")
_RAG_DIR = os.path.join(_PROJECT_ROOT, "memory", "rag")

# Lazy-initialized ChromaDB client and collection
_chroma_client = None
_collection = None

OLLAMA_EMBED_MODEL = "embeddinggemma:latest"
OLLAMA_BASE_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Identity — permanent core files (never wiped)
# ---------------------------------------------------------------------------

def read_identity(filename: str) -> str:
    """Read a permanent identity file (e.g. 'MINA.md'). Returns empty string if missing."""
    path = os.path.join(_IDENTITY_DIR, filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# KAG — file-based knowledge
# ---------------------------------------------------------------------------

def read_kag(filename: str) -> str:
    """Read a KAG file by name (e.g. 'RELATIONSHIP.md'). Returns empty string if missing."""
    path = os.path.join(_KAG_DIR, filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_kag(filename: str, content: str) -> None:
    """Write/overwrite a KAG file."""
    os.makedirs(_KAG_DIR, exist_ok=True)
    path = os.path.join(_KAG_DIR, filename)
    with open(path, "w") as f:
        f.write(content)


def list_knowledge() -> list[str]:
    """Return all filenames in the KNOWLEDGE/ subdirectory."""
    knowledge_dir = os.path.join(_KAG_DIR, "KNOWLEDGE")
    if not os.path.isdir(knowledge_dir):
        return []
    return [f for f in os.listdir(knowledge_dir) if f.endswith(".md")]


def read_knowledge(filename: str) -> str:
    """Read a file from KNOWLEDGE/."""
    path = os.path.join(_KAG_DIR, "KNOWLEDGE", filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_knowledge(filename: str, content: str) -> None:
    """Write a file to KNOWLEDGE/."""
    knowledge_dir = os.path.join(_KAG_DIR, "KNOWLEDGE")
    os.makedirs(knowledge_dir, exist_ok=True)
    with open(os.path.join(knowledge_dir, filename), "w") as f:
        f.write(content)


def build_kag_context() -> str:
    """Assemble the full KAG context block for the subconscious prompt."""
    parts = []

    # Identity files — read from permanent identity/ dir
    mina = read_identity("MINA.md")
    if mina:
        parts.append(f"## Character\n{mina}")

    appearance = read_identity("APPEARANCE.md")
    if appearance:
        parts.append(f"## Appearance\n{appearance}")

    relationship = read_kag("RELATIONSHIP.md")
    if relationship:
        parts.append(f"## Relationship with User\n{relationship}")

    pending = read_kag("PENDING.md")
    if pending:
        parts.append(f"## Pending\n{pending}")

    knowledge_files = list_knowledge()
    for fname in sorted(knowledge_files):
        content = read_knowledge(fname)
        if content:
            parts.append(f"## Knowledge: {fname}\n{content}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# RAG — ChromaDB episodic memory
# ---------------------------------------------------------------------------

class _OllamaEmbeddingFunction:
    """ChromaDB-compatible embedding function using local Ollama."""

    def name(self) -> str:
        return "ollama"

    def _embed(self, texts: list[str]) -> list[list[float]]:
        import urllib.request
        import json as _json

        embeddings = []
        for text in texts:
            payload = _json.dumps({"model": OLLAMA_EMBED_MODEL, "prompt": text}).encode()
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read())
            embeddings.append(result["embedding"])
        return embeddings

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)


def _get_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        return None

    os.makedirs(_RAG_DIR, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=_RAG_DIR)

    ef = _OllamaEmbeddingFunction()

    _collection = _chroma_client.get_or_create_collection(
        name="mina_experiences",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def _reset_collection() -> None:
    """Clear cached collection so it gets re-initialized on next call."""
    global _chroma_client, _collection
    _chroma_client = None
    _collection = None


def rag_wipe() -> None:
    """
    Completely destroy the RAG store. Deletes the on-disk ChromaDB directory
    and resets the in-process cache. The store will be recreated empty on next use.
    """
    import shutil
    _reset_collection()
    if os.path.exists(_RAG_DIR):
        shutil.rmtree(_RAG_DIR)


def rag_add(text: str, metadata: Optional[dict] = None) -> None:
    """Embed and store an episodic memory."""
    collection = _get_collection()
    if collection is None:
        return

    doc_id = f"exp_{int(time.time() * 1000)}"
    meta = {"timestamp": time.time()}
    if metadata:
        meta.update(metadata)

    try:
        collection.add(documents=[text], ids=[doc_id], metadatas=[meta])
    except Exception as e:
        if "does not exist" in str(e):
            _reset_collection()
            collection = _get_collection()
            if collection:
                collection.add(documents=[text], ids=[doc_id], metadatas=[meta])
        else:
            raise


def rag_query(query: str, n_results: int = 5) -> list[str]:
    """Retrieve the most relevant episodic memories for a query. Returns list of strings."""
    collection = _get_collection()
    if collection is None:
        return []

    try:
        count = collection.count()
        if count == 0:
            return []
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        return results.get("documents", [[]])[0]
    except Exception as e:
        if "does not exist" in str(e):
            _reset_collection()
        return []


def build_rag_context(query: str, n_results: int = 5) -> str:
    """Retrieve relevant memories and format as a context block."""
    memories = rag_query(query, n_results)
    if not memories:
        return ""
    lines = "\n".join(f"- {m}" for m in memories)
    return f"## Relevant Memories\n{lines}"
