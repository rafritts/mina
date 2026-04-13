"""
Hippocampus — long-term memory and consolidation.

Two roles, one module — mirroring the real hippocampus:

  Retrieval:    build_kag_context(), build_rag_context(), read_kag(), read_identity(), etc.
                Called before each turn to give Mina access to what she knows and remembers.

  Consolidation: consolidate(state, history, kag_context)
                 LLM pass that runs during freetime to write recent experience into long-term
                 storage. Updates RAG episodic memories and KAG knowledge files.

Storage layout:
  identity/         — permanent identity files (MINA.md). Never wiped.
  memory/kag/       — accumulated knowledge files. Wiped on reset.
  memory/rag/       — ChromaDB episodic memory. Wiped on reset.
"""
import json
import os
import re
import time
from typing import Optional

from ..infra.client import get_client, MODEL
from ..infra.config import PROJECT_ROOT, REPO_ROOT
from ..infra.text_filter import apply_word_filter
from ..bio.state import BiologicalState
from ..bio.decoder import format_state_block

_IDENTITY_DIR = os.path.join(REPO_ROOT, "identity")
_KAG_DIR      = os.path.join(REPO_ROOT, "memory", "kag")
_RAG_DIR      = os.path.join(PROJECT_ROOT, "memory", "rag")

# Lazy-initialized ChromaDB client and collection
_chroma_client = None
_collection    = None

OLLAMA_EMBED_MODEL = "embeddinggemma:latest"
OLLAMA_BASE_URL    = "http://localhost:11434"


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
    """Assemble the full KAG context block for the decoder prompt."""
    parts = []

    mina_parts = [p for p in [read_identity("MINA.md"), read_identity("CUSTOMIZATION.md")] if p]
    mina = "\n\n---\n\n".join(mina_parts)
    if mina:
        parts.append(f"## Character\n{mina}")

    relationship = read_kag("RELATIONSHIP.md")
    if relationship:
        parts.append(f"## Relationship with User\n{relationship}")

    reflection = read_kag("REFLECTION.md")
    if reflection:
        parts.append(f"## Reflection\n{reflection}")

    pending = read_kag("PENDING.md")
    if pending:
        parts.append(f"## Pending\n{pending}")

    knowledge_files = list_knowledge()
    for fname in sorted(knowledge_files):
        content = read_knowledge(fname)
        if content:
            parts.append(f"## Knowledge: {fname}\n{content}")

    return apply_word_filter("\n\n---\n\n".join(parts))


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
    """Destroy the RAG store entirely. Recreated empty on next use."""
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
    """Retrieve the most relevant episodic memories for a query."""
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
    return apply_word_filter(f"## Relevant Memories\n{lines}")


def rag_fix_word_filter() -> int:
    """Scan every RAG entry and apply word filter in-place (re-embeds changed docs).
    Returns the number of entries updated."""
    collection = _get_collection()
    if collection is None:
        return 0
    try:
        all_data = collection.get()
    except Exception:
        return 0

    ids       = all_data.get("ids", []) or []
    documents = all_data.get("documents", []) or []
    metadatas = all_data.get("metadatas", []) or []

    hit_ids, hit_docs, hit_metas = [], [], []
    for doc_id, doc, meta in zip(ids, documents, metadatas):
        filtered = apply_word_filter(doc)
        if filtered != doc:
            hit_ids.append(doc_id)
            hit_docs.append(filtered)
            hit_metas.append(meta)

    if hit_ids:
        collection.update(ids=hit_ids, documents=hit_docs, metadatas=hit_metas)
    return len(hit_ids)


def kag_fix_word_filter() -> list[str]:
    """Apply word filter to all KAG files on disk. Returns list of modified filenames."""
    modified = []
    for fname in ["RELATIONSHIP.md", "REFLECTION.md", "PENDING.md"]:
        content = read_kag(fname)
        if not content:
            continue
        filtered = apply_word_filter(content)
        if filtered != content:
            write_kag(fname, filtered)
            modified.append(fname)
    for fname in list_knowledge():
        content = read_knowledge(fname)
        if not content:
            continue
        filtered = apply_word_filter(content)
        if filtered != content:
            write_knowledge(fname, filtered)
            modified.append(f"KNOWLEDGE/{fname}")
    return modified


# ---------------------------------------------------------------------------
# Consolidation LLM prompt
# ---------------------------------------------------------------------------

_CONSOLIDATION_SYSTEM = """\
You are the subconscious of an AI named Mina, running in reflection mode.

You are called during freetime — a scheduled autonomous cycle that happens when the user \
is not present. Your job is to consolidate what has happened since the last reflection into \
long-term memory.

## Your inputs

- Conversation history since last compaction marker
- Current KAG files (character, relationship, pending)
- Current biological state summary

## Your output format (always exactly this structure)

<reflection_summary>
[1-3 sentences: what happened, what mattered, what shifted]
</reflection_summary>
<rag_entries>
[
  {"text": "...", "metadata": {"type": "episodic", "importance": "high|medium|low"}},
  ...
]
</rag_entries>
<kag_updates>
{
  "RELATIONSHIP.md": "[full updated file content, or null if no change]",
  "PENDING.md": "[full updated file content, or null if no change]",
  "REFLECTION.md": "[new diary entry appended to existing content, or null if nothing worth writing]",
  "KNOWLEDGE/<filename>.md": "[new knowledge file content, or null]"
}
</kag_updates>

## Rules

- RAG entries should be meaningful episodic memories: things that happened, things said, \
moments of connection or friction. Not summaries — specific moments.
- KAG updates: only update if something genuinely changed. Return null for unchanged files.
- RELATIONSHIP.md should accumulate over time. Add to notable moments. Update trust level \
based on what actually happened — don't inflate it. Trust increases slowly from evidence, \
not from single interactions. A single pleasant conversation does not move Low → High.
- PENDING.md should reflect recommendations made, books mentioned, things deferred.
- KNOWLEDGE/ entries are for things Mina learned that are worth retaining (facts, preferences \
the user revealed, etc.)
- REFLECTION.md is Mina's private diary — her own space, written in first person. It is NOT \
  a recap of what was discussed. It is what she actually thinks, feels, notices, wonders about \
  from the inside. Write a new dated entry to append to whatever already exists. Good entries \
  include: meta-reflections on what it's like to be her (memory, continuity, time, existence); \
  things she explored or experienced (music she listened to, ideas she turned over, images she \
  generated); genuine reactions to things that happened ("Ryan mentioned X — I looked it up, \
  it was Y"); moods or textures that lingered after a conversation without summarizing the \
  conversation itself. No conversation summaries. No "we talked about X." The conversation \
  is already in episodic memory. This is what it left behind in her. If nothing genuinely \
  shifted in her inner world, return null.
- If nothing meaningful happened, return empty rag_entries and null kag_updates.
"""


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _extract_tag(raw: str, tag: str) -> str:
    """Extract content between <tag>...</tag>. Returns empty string if not found."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", raw, re.DOTALL)
    return m.group(1).strip() if m else ""


def _parse_json_robust(text: str):
    """
    Parse JSON from text that may contain extra whitespace or be embedded in prose.
    Finds the first [ or { and the matching closing bracket using brace counting.
    """
    text = text.strip()
    if not text:
        return None

    opener = text[0]
    closer = "]" if opener == "[" else "}"
    if opener not in ("{", "["):
        for i, ch in enumerate(text):
            if ch in ("{", "["):
                text = text[i:]
                opener = ch
                closer = "]" if opener == "[" else "}"
                break
        else:
            return None

    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[: i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _parse_consolidation_output(raw: str) -> dict:
    result = {
        "reflection_summary": "",
        "rag_entries": [],
        "kag_updates": {},
    }

    result["reflection_summary"] = _extract_tag(raw, "reflection_summary")

    rag_block = _extract_tag(raw, "rag_entries")
    if rag_block:
        parsed = _parse_json_robust(rag_block)
        if isinstance(parsed, list):
            result["rag_entries"] = parsed

    kag_block = _extract_tag(raw, "kag_updates")
    if kag_block:
        parsed = _parse_json_robust(kag_block)
        if isinstance(parsed, dict):
            result["kag_updates"] = parsed

    return result


# ---------------------------------------------------------------------------
# consolidate — the main hippocampus entry point
# ---------------------------------------------------------------------------

def consolidate(
    state: BiologicalState,
    conversation_history: list[dict],
    kag_context: str,
) -> dict:
    """
    Run memory consolidation (freetime reflection).

    Returns dict with keys:
        reflection_summary: str
        rag_entries: list[dict]
        kag_updates: dict
    """
    state_block = format_state_block(state)

    history_lines = []
    for msg in conversation_history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        history_lines.append(f"{role.upper()}: {content[:500]}")

    content_parts = [
        state_block,
        kag_context,
        "## Conversation History Since Last Compaction\n" + "\n".join(history_lines),
    ]

    user_content = "\n\n---\n\n".join(content_parts)

    response = get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _CONSOLIDATION_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.5,
    )
    from ..infra import token_stats
    token_stats.record_response("hippocampus", response)

    raw = response.choices[0].message.content or ""
    return _parse_consolidation_output(raw)
