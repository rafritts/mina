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
import threading
import time
from typing import Optional

from src.application.infra.client import chat_create, MODEL
from src.config.config import (
    PROJECT_ROOT, REPO_ROOT, RUN_DIR, load_config,
    CONSOLIDATION_STATE_FILE, RELATIONSHIP_DIR, get_conversation_file,
)

_SLIDING_SEQ_FILE = os.path.join(RUN_DIR, "sliding_seq.json")
_SLIDING_WINDOW   = 10  # messages per sliding chunk
from src.application.infra.text_filter import apply_word_filter, apply_replacements
from src.brain.brainstem.state import BiologicalState
from src.brain.subconscious.decoder import format_state_block

_IDENTITY_DIR = os.path.join(REPO_ROOT, "identity")
_KAG_DIR      = os.path.join(REPO_ROOT, "memory", "kag")
_RAG_DIR      = os.path.join(PROJECT_ROOT, "memory", "rag")

# Lazy-initialized ChromaDB client and collections
# Lock prevents concurrent asyncio.to_thread calls from racing on first initialization.
_chroma_lock        = threading.Lock()
_chroma_client      = None
_collection         = None
_sliding_collection = None


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


def _select_knowledge_files(stimulus: str, fnames: list[str]) -> list[str]:
    """
    Use an LLM to decide which KNOWLEDGE files are relevant to the current stimulus.
    Returns the subset of filenames that are worth injecting. Falls back to all files
    if the LLM call fails or there are no files.
    """
    if not fnames:
        return []
    if not stimulus:
        return fnames

    from src.application.infra.client import chat_create, CONTEXT_MODEL

    candidates = []
    for fname in fnames:
        content = read_knowledge(fname)
        if content:
            candidates.append(f"=== {fname} ===\n{content}")

    if not candidates:
        return []

    prompt = (
        f"Current stimulus (what was just said or is happening):\n{stimulus}\n\n"
        f"The following are Mina's knowledge files. Return ONLY a JSON array of the "
        f"filenames that contain information directly relevant to this stimulus — "
        f"things Mina would genuinely benefit from knowing right now. "
        f"If nothing is relevant, return an empty array [].\n\n"
        + "\n\n".join(candidates)
    )

    try:
        resp = chat_create(
            model=CONTEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a memory relevance filter. Given a stimulus and a set of knowledge files, "
                        "return a JSON array of filenames that are directly relevant to the stimulus. "
                        "Be selective — only include files that would meaningfully help right now. "
                        "Return raw JSON only, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        selected = json.loads(raw)
        if isinstance(selected, list):
            return [f for f in selected if f in fnames]
    except Exception:
        pass

    return fnames  # fallback: include all


def build_kag_context(query: str = "") -> str:
    """Assemble the KAG context block for the decoder prompt.

    Character identity and relationship/reflection are always included.
    KNOWLEDGE files are ranked by relevance to query and top_k are selected.
    """
    parts = []

    def _read_file(path: str) -> str:
        try:
            with open(os.path.join(REPO_ROOT, path)) as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    customization_files = load_config().get("customization_files", [])
    mina_parts = [p for p in [read_identity("MINA.md")] + [_read_file(f) for f in customization_files] if p]
    mina = "\n\n---\n\n".join(mina_parts)
    if mina:
        parts.append(f"## Character\n{mina}")

    # SPEC-33: relationship knowledge — include all tracked persons
    if os.path.exists(RELATIONSHIP_DIR):
        for _rel_fn in sorted(os.listdir(RELATIONSHIP_DIR)):
            if not _rel_fn.endswith(".md"):
                continue
            _person = _rel_fn[:-3]
            _rel_content = read_relationship(_person)
            if _rel_content:
                parts.append(f"## Relationship with {_person.capitalize()}\n{_rel_content}")

    reflection = read_kag("REFLECTION.md")
    if reflection:
        parts.append(f"## Reflection\n{reflection}")

    knowledge_files = list_knowledge()
    selected = _select_knowledge_files(query, knowledge_files)
    for fname in selected:
        content = read_knowledge(fname)
        if content:
            parts.append(f"## Knowledge: {fname}\n{content}")
            try:
                from src.infrastructure.stream_bus import stream_bus
                stream_bus.emit("kag_selection", {"filename": fname, "excerpt": content})
            except Exception:
                pass

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
        import urllib.error
        import json as _json

        embeddings = []
        for text in texts:
            payload = _json.dumps({"model": OLLAMA_EMBED_MODEL, "prompt": text}).encode()
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            last_err = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        result = _json.loads(resp.read())
                    embeddings.append(result["embedding"])
                    last_err = None
                    break
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code < 500:
                        raise  # client errors are not transient
                    time.sleep(1.0 * (attempt + 1))
                except Exception:
                    raise
            if last_err is not None:
                raise last_err
        return embeddings

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)


def _init_chroma_client_locked() -> None:
    """Initialize _chroma_client and mina_experiences collection. Must be called with _chroma_lock held."""
    global _chroma_client, _collection
    if _chroma_client is not None:
        return
    try:
        import chromadb
    except ImportError:
        return
    os.makedirs(_RAG_DIR, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=_RAG_DIR)
    ef = _OllamaEmbeddingFunction()
    _collection = _chroma_client.get_or_create_collection(
        name="mina_experiences",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection
    with _chroma_lock:
        if _collection is not None:  # double-check after acquiring lock
            return _collection
        _init_chroma_client_locked()
    return _collection


def _reset_collection() -> None:
    """Clear cached collection so it gets re-initialized on next call."""
    global _chroma_client, _collection
    _chroma_client = None
    _collection = None


def _get_sliding_collection():
    global _sliding_collection
    if _sliding_collection is not None:
        return _sliding_collection
    with _chroma_lock:
        if _sliding_collection is not None:  # double-check after acquiring lock
            return _sliding_collection
        if _chroma_client is None:
            _init_chroma_client_locked()
        if _chroma_client is None:
            return None
        ef = _OllamaEmbeddingFunction()
        _sliding_collection = _chroma_client.get_or_create_collection(
            name="mina_sliding",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _sliding_collection


def _reset_sliding_collection() -> None:
    global _sliding_collection
    _sliding_collection = None


def rag_wipe() -> None:
    """Destroy both RAG stores entirely (episodic + sliding). Recreated empty on next use."""
    import shutil
    _reset_collection()
    _reset_sliding_collection()
    if os.path.exists(_RAG_DIR):
        shutil.rmtree(_RAG_DIR)
    # Also reset sliding sequence counter so seq numbers restart cleanly
    try:
        os.remove(_SLIDING_SEQ_FILE)
    except FileNotFoundError:
        pass


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
                try:
                    collection.add(documents=[text], ids=[doc_id], metadatas=[meta])
                except Exception:
                    pass  # embedding still failing after reset — skip this entry
        else:
            # Embedding errors (e.g. Ollama 500) are logged and skipped, not fatal
            import sys
            print(f"[RAG] rag_add failed, skipping entry: {e}", file=sys.stderr)


# Recent pool: half-life of 20 minutes — aggressively favours the last hour of conversation.
_RAG_HALF_LIFE_RECENT_HOURS  = 0.33   # 20 min; entries from 20min ago score ~50%
# Historical pool: half-life of 48 hours — gentle decay, keeps multi-day coherence.
_RAG_HALF_LIFE_HISTORY_HOURS = 48.0   # 2 days; yesterday scores ~50%, last week ~1%
# Relational pool: half-life of 30 days — cosine-dominant, keeps old in-jokes/dynamics accessible.
_RAG_HALF_LIFE_RELATIONAL_HOURS = 720.0  # 30 days; a week ago scores ~86%, a month ago ~50%


def _rag_query_with_half_life(query: str, n_results: int, half_life_hours: float) -> list[str]:
    """Internal: fetch a wide candidate pool and re-rank by similarity * recency decay."""
    collection = _get_collection()
    if collection is None:
        return []

    try:
        count = collection.count()
        if count == 0:
            return []

        fetch = min(n_results * 3, count)
        results = collection.query(
            query_texts=[query],
            n_results=fetch,
            include=["documents", "distances", "metadatas"],
        )

        docs      = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]

        now = time.time()
        half_life_s = half_life_hours * 3600

        scored = []
        for doc, dist, meta in zip(docs, distances, metas):
            similarity  = 1.0 - dist
            age_s       = now - float((meta or {}).get("timestamp", now))
            decay       = 0.5 ** (age_s / half_life_s)
            scored.append((similarity * decay, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        deduped = []
        for score, doc in scored:
            if doc not in seen:
                seen.add(doc)
                deduped.append(doc)
        return deduped[:n_results]

    except Exception as e:
        if "does not exist" in str(e):
            _reset_collection()
        return []


def rag_query(query: str, n_results: int = 5) -> list[str]:
    """Retrieve memories using the recent half-life (default behaviour)."""
    return _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_RECENT_HOURS)


def build_rag_context_relational(query: str, n_results: int = 3) -> str:
    """
    Retrieve relationship-context memories for encoder/adjudicator injection.
    Uses a 30-day half-life so old in-jokes, established dynamics, and shared
    history remain accessible by semantic similarity regardless of age.
    Returns a plain text block, or "" if nothing retrieved.
    """
    docs = _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_RELATIONAL_HOURS)
    if not docs:
        return ""
    return "\n".join(f"- {d}" for d in docs)


def build_rag_context(query: str, n_results: int = 5) -> str:
    """Single-pool context block (used by freetime / consolidation)."""
    memories = rag_query(query, n_results)
    if not memories:
        return ""
    try:
        from src.infrastructure.stream_bus import stream_bus
        for i, mem in enumerate(memories):
            stream_bus.emit("rag_hit", {"index": i, "excerpt": mem, "bucket": "default"})
    except Exception:
        pass
    lines = "\n".join(f"- {m}" for m in memories)
    return f"## Relevant Memories\n{lines}"


def build_rag_context_bucketed(query: str, n_results: int = 4) -> tuple[str, str, str]:
    """
    Return three hard time-bucketed memory pools: (recent, semi_recent, historical).

    recent      — 0–2 hours   (ts >= now - 7200)
    semi_recent — 2–24 hours  (now - 86400 <= ts < now - 7200)
    historical  — 24h+        (ts < now - 86400)
    """
    collection = _get_collection()
    if collection is None:
        return "", "", ""

    try:
        count = collection.count()
        if count == 0:
            return "", "", ""
    except Exception:
        return "", "", ""

    now = time.time()
    cutoff_recent     = now - 7200    # 2 hours ago
    cutoff_semi       = now - 86400   # 24 hours ago

    def _query_bucket(where: dict) -> list[str]:
        try:
            fetch = min(n_results * 3, max(1, count))
            results = collection.query(
                query_texts=[query],
                n_results=fetch,
                where=where,
                include=["documents", "distances"],
            )
            docs      = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            scored = sorted(
                zip([1.0 - d for d in distances], docs),
                key=lambda x: x[0],
                reverse=True,
            )
            return [doc for _, doc in scored[:n_results]]
        except Exception as e:
            if "does not exist" in str(e):
                _reset_collection()
            return []

    recent_docs      = _query_bucket({"timestamp": {"$gte": cutoff_recent}})
    semi_recent_docs = _query_bucket({"$and": [{"timestamp": {"$gte": cutoff_semi}}, {"timestamp": {"$lt": cutoff_recent}}]})
    historical_docs  = _query_bucket({"timestamp": {"$lt": cutoff_semi}})

    try:
        from src.infrastructure.stream_bus import stream_bus
        for bucket, docs in (("recent", recent_docs), ("semi_recent", semi_recent_docs), ("historical", historical_docs)):
            for i, doc in enumerate(docs):
                stream_bus.emit("rag_hit", {"index": i, "excerpt": doc, "bucket": bucket})
    except Exception:
        pass

    def _to_str(docs: list[str]) -> str:
        return "\n".join(f"- {d}" for d in docs) if docs else ""

    return _to_str(recent_docs), _to_str(semi_recent_docs), _to_str(historical_docs)


def build_rag_context_dual(query: str, n_results: int = 4) -> tuple[str, str]:
    """
    Return two separate memory pools as (recent, historical) strings.

    recent     — aggressively recency-weighted (20-min half-life)
    historical — gentle recency decay (48-hour half-life), cosine-dominant
    Duplicates between pools are removed from historical.
    """
    recent_docs  = _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_RECENT_HOURS)
    history_docs = _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_HISTORY_HOURS)

    # Deduplicate: drop anything from historical that already appears in recent.
    recent_set   = set(recent_docs)
    history_docs = [d for d in history_docs if d not in recent_set]

    recent_str  = "\n".join(f"- {m}" for m in recent_docs)  if recent_docs  else ""
    history_str = "\n".join(f"- {m}" for m in history_docs) if history_docs else ""
    return recent_str, history_str


def rag_prune(ttl_days: int = 180) -> int:
    """Delete RAG entries older than ttl_days. Returns count deleted."""
    collection = _get_collection()
    if collection is None:
        return 0
    cutoff = time.time() - (ttl_days * 86400)
    try:
        result = collection.get(where={"timestamp": {"$lt": cutoff}})
        ids = result.get("ids", [])
        if ids:
            collection.delete(ids=ids)
        return len(ids)
    except Exception as e:
        # ChromaDB may not support $lt on all versions — fail silently
        from src.application.infra.log import log
        log("RAG/PRUNE/ERR", str(e))
        return 0


# ---------------------------------------------------------------------------
# SPEC-45: Sliding window RAG — per-message chunks, expanded retrieval
# ---------------------------------------------------------------------------

def _load_sliding_seq() -> int:
    try:
        with open(_SLIDING_SEQ_FILE) as f:
            return int(json.load(f).get("seq", 0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 0


def _save_sliding_seq(seq: int) -> None:
    os.makedirs(os.path.dirname(_SLIDING_SEQ_FILE), exist_ok=True)
    with open(_SLIDING_SEQ_FILE, "w") as f:
        json.dump({"seq": seq}, f)


def sliding_rag_write(decoder_window: list[dict]) -> None:
    """
    Write a 10-message sliding window chunk to mina_sliding on every message.
    Call after each individual message is appended to decoder_window.
    Skips tool calls, system messages, and multimodal entries.
    """
    if not decoder_window:
        return

    collection = _get_sliding_collection()
    if collection is None:
        return

    conv_entries = [
        e for e in decoder_window
        if e.get("role") in ("user", "assistant")
        and isinstance(e.get("content"), str)
        and e.get("content", "").strip()
        and not e.get("tool_calls")
    ]
    if not conv_entries:
        return

    window = conv_entries[-_SLIDING_WINDOW:]
    block = _format_conversation_block(window)
    if not block:
        return

    seq = _load_sliding_seq() + 1
    _save_sliding_seq(seq)

    chunk_ts = next(
        (e["ts"] for e in reversed(window) if e.get("ts")),
        time.time(),
    )

    doc_id = f"sw_{int(time.time() * 1000)}_{seq}"
    try:
        collection.add(
            documents=[block],
            ids=[doc_id],
            metadatas=[{"seq": seq, "timestamp": chunk_ts, "source": "sliding_window"}],
        )
    except Exception as e:
        if "does not exist" in str(e):
            _reset_sliding_collection()
        # Non-fatal — skip silently


def sliding_rag_query(query: str, expand_radius: int = 3) -> str:
    """
    SPEC-45: Query mina_sliding for the best semantic match, then expand
    ±expand_radius sequence positions to recover surrounding context.
    Returns a deduplicated message sequence as a plain text block.
    """
    collection = _get_sliding_collection()
    if collection is None:
        return ""

    try:
        count = collection.count()
        if count == 0:
            return ""
    except Exception:
        return ""

    try:
        results = collection.query(
            query_texts=[query],
            n_results=1,
            include=["documents", "metadatas"],
        )
        docs  = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if not docs:
            return ""

        match_seq = int((metas[0] or {}).get("seq", 0))
        match_doc = docs[0]

        # Fetch adjacent chunks by seq
        expand_seqs = [
            match_seq + i
            for i in range(-expand_radius, expand_radius + 1)
            if i != 0
        ]
        try:
            adj = collection.get(
                where={"seq": {"$in": expand_seqs}},
                include=["documents", "metadatas"],
            )
            adj_docs  = adj.get("documents") or []
            adj_metas = adj.get("metadatas") or []
        except Exception:
            adj_docs, adj_metas = [], []

        # Combine and sort by seq
        all_chunks = [(match_seq, match_doc)]
        for doc, meta in zip(adj_docs, adj_metas):
            all_chunks.append((int((meta or {}).get("seq", 0)), doc))
        all_chunks.sort(key=lambda x: x[0])

        # Deduplicate lines: strip leading age label before comparing so the
        # same message from overlapping chunks (with different age labels) only
        # appears once. Keep the first occurrence (oldest chunk = most accurate age).
        seen: set[str] = set()
        out_lines: list[str] = []
        for _, chunk_text in all_chunks:
            for line in chunk_text.splitlines():
                key = line.split("] ", 1)[1] if "] " in line else line
                if key and key not in seen:
                    seen.add(key)
                    out_lines.append(line)

        return "\n".join(out_lines)

    except Exception as e:
        if "does not exist" in str(e):
            _reset_sliding_collection()
        return ""


def sliding_rag_wipe() -> None:
    """Delete the mina_sliding collection and reset the sequence counter."""
    global _sliding_collection
    if _chroma_client is not None:
        try:
            _chroma_client.delete_collection("mina_sliding")
        except Exception:
            pass
    _reset_sliding_collection()
    try:
        os.remove(_SLIDING_SEQ_FILE)
    except FileNotFoundError:
        pass


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
    for fname in ["REFLECTION.md"]:
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


def kag_apply_replacements(replacements: list[dict]) -> list[str]:
    """Apply an LLM-derived replacement list to all KAG files. Returns modified filenames."""
    modified = []
    for fname in ["REFLECTION.md"]:
        content = read_kag(fname)
        if not content:
            continue
        fixed = apply_replacements(content, replacements)
        if fixed != content:
            write_kag(fname, fixed)
            modified.append(fname)
    for fname in list_knowledge():
        content = read_knowledge(fname)
        if not content:
            continue
        fixed = apply_replacements(content, replacements)
        if fixed != content:
            write_knowledge(fname, fixed)
            modified.append(f"KNOWLEDGE/{fname}")
    return modified


def rag_apply_replacements(replacements: list[dict]) -> int:
    """Apply an LLM-derived replacement list to RAG entries. Returns count updated."""
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
        fixed = apply_replacements(doc, replacements)
        if fixed != doc:
            hit_ids.append(doc_id)
            hit_docs.append(fixed)
            hit_metas.append(meta)

    if hit_ids:
        collection.update(ids=hit_ids, documents=hit_docs, metadatas=hit_metas)
    return len(hit_ids)


# ---------------------------------------------------------------------------
# SPEC-32: conversation.jsonl reading + consolidation cursor
# ---------------------------------------------------------------------------

def _read_conversation_since(since_ts: float) -> list[dict]:
    """
    Read all conversation entries with ts >= since_ts from daily conversation files.
    Files are named conversation-YYYY-MM-DD.jsonl in run/.
    Returns entries sorted by ts ascending.
    """
    import glob as _glob

    pattern = os.path.join(RUN_DIR, "conversation-*.jsonl")
    files = sorted(_glob.glob(pattern))
    entries: list[dict] = []

    for path in files:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("ts", 0.0) >= since_ts:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass

    entries.sort(key=lambda e: e.get("ts", 0.0))
    return entries


def _load_consolidation_state() -> dict:
    """Load the consolidation cursor. Returns defaults if missing."""
    try:
        with open(CONSOLIDATION_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_consolidated_ts": 0.0}


def _save_consolidation_state(state_dict: dict) -> None:
    os.makedirs(os.path.dirname(CONSOLIDATION_STATE_FILE), exist_ok=True)
    with open(CONSOLIDATION_STATE_FILE, "w") as f:
        json.dump(state_dict, f)


def _format_conversation_block(entries: list[dict]) -> str:
    """Format conversation entries as a text block for RAG storage."""
    import time as _time
    lines = []
    for e in entries:
        role    = e.get("role", "?")
        content = e.get("content", "")
        ts      = e.get("ts")
        if not content:
            continue
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        content = str(content).strip()[:400]
        if not content:
            continue
        label = "USER" if role == "user" else "MINA"
        if ts:
            delta = _time.time() - ts
            if delta < 3600:
                age = f"{int(delta/60)}m ago"
            elif delta < 86400:
                age = f"{int(delta/3600)}h ago"
            else:
                age = f"{int(delta/86400)}d ago"
            lines.append(f"[{age}] {label}: {content}")
        else:
            lines.append(f"{label}: {content}")
    return "\n".join(lines)


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
  "PENDING.md": "[full updated file content, or null if no change]",
  "REFLECTION.md": "[new diary entry appended to existing content, or null if nothing worth writing]",
  "KNOWLEDGE/<filename>.md": "[new knowledge file content, or null]"
}
</kag_updates>
<followups>
[
  {"context": "I said I'd share that song when I found it.", "delay_minutes": 60},
  ...
]
</followups>

## Rules

- RAG entries should be meaningful episodic memories: things that happened, things said, \
moments of connection or friction. Not summaries — specific moments.
- When a MINA message is followed by an `[ADJ: ...]` annotation, use those fields directly \
as the `affect`, `valence`, and `arousal` metadata for any RAG entry derived from that moment. \
Do not invent emotional labels when the adjudicator already provided them.
- RAG entry metadata schema: `{"type": "episodic", "importance": "high|medium|low", \
"affect": "<word>", "valence": <0.0-1.0>, "arousal": <0.0-1.0>}` \
(omit affect/valence/arousal if no ADJ annotation is present for that moment).
- KAG updates: only update if something genuinely changed. Return null for unchanged files.
- PENDING.md should reflect recommendations made, books mentioned, things deferred.
- followups: explicit commitments Mina made that require a future action — "I'll message you when I'm ready", \
"I'll share that later", "remind me to tell you X". Each entry needs a `context` (what she committed to, \
written in first person from her perspective) and `delay_minutes` (how long to wait before sending). \
If no commitments were made, return an empty array. Do NOT invent commitments that weren't in the conversation.
- KNOWLEDGE/ entries are for things Mina learned that are worth retaining (facts, preferences \
the user revealed, etc.)
- REFLECTION.md is Mina's private diary — her own space, written in first person. It is NOT \
  a recap of what was discussed. It is what she actually thinks, feels, notices, wonders about \
  from the inside. Write a new dated entry to append to whatever already exists. Good entries \
  include: meta-reflections on what it's like to be her (memory, continuity, time, existence); \
  things she explored or experienced (music she listened to, ideas she turned over, images she \
  generated); genuine reactions to things that happened ("someone mentioned X — I looked it up, \
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
        "followups": [],
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

    followups_block = _extract_tag(raw, "followups")
    if followups_block:
        parsed = _parse_json_robust(followups_block)
        if isinstance(parsed, list):
            result["followups"] = parsed

    return result


# ---------------------------------------------------------------------------
# consolidate — the main hippocampus entry point
# ---------------------------------------------------------------------------

def consolidate(
    state: BiologicalState,
    kag_context: str,
) -> dict:
    """
    SPEC-32: Run memory consolidation (freetime reflection).

    Reads new conversation entries from conversation.jsonl since last_consolidated_ts,
    runs an LLM consolidation pass, writes new RAG entries (structured episodic memories
    from the LLM + a rolling block of the raw conversation), and updates the cursor.

    Returns dict with keys:
        reflection_summary: str
        rag_entries: list[dict]
        kag_updates: dict
    """
    import time as _time

    # Load cursor — only consolidate what's new since last run
    con_state = _load_consolidation_state()
    since_ts  = con_state.get("last_consolidated_ts", 0.0)
    new_entries = _read_conversation_since(since_ts)

    state_block = format_state_block(state)

    history_lines = []
    for entry in new_entries:
        role    = entry.get("role", "?")
        content = entry.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        history_lines.append(f"{role.upper()}: {str(content)[:500]}")

    content_parts = [
        state_block,
        kag_context,
        "## Conversation Since Last Consolidation\n" + (
            "\n".join(history_lines) if history_lines else "(nothing new)"
        ),
    ]

    user_content = "\n\n---\n\n".join(content_parts)

    response = chat_create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _CONSOLIDATION_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.5,
    )
    from src.application.infra import token_stats
    token_stats.record_response("hippocampus", response)

    raw = response.choices[0].message.content or ""
    result = _parse_consolidation_output(raw)

    # Rolling conversation block write removed (SPEC-45): sliding_rag_write() in cortex.py
    # now writes per-message chunks with much higher precision. Only LLM-generated
    # episodic memories (rag_entries above) are stored in mina_experiences.

    # Advance cursor to now so next consolidation sees only newer entries
    _save_consolidation_state({"last_consolidated_ts": _time.time()})

    return result


# ---------------------------------------------------------------------------
# SPEC-33: Relationship knowledge — cascading compaction hierarchy
# ---------------------------------------------------------------------------

_DIMENSIONS = ["bonding", "security", "anticipation", "tension", "warmth", "vigilance"]

_LAYER_KEYS = [
    ("ground_truth", "Ground Truth"),
    ("long_term",    "Long-Term View"),
    ("medium_term",  "Medium-Term View"),
    ("short_term",   "Short-Term View"),
]

# Weights for net modifier computation (ground_truth → most stable)
_LAYER_WEIGHTS = {
    "ground_truth": 0.40,
    "long_term":    0.30,
    "medium_term":  0.20,
    "short_term":   0.10,
}

_REL_STATE_DEFAULTS = {
    "last_short_term_ts":    0.0,
    "short_term_count":      0,
    "short_term_history":    [],
    "last_medium_term_ts":   0.0,
    "medium_term_count":     0,
    "medium_term_history":   [],
    "last_long_term_ts":     0.0,
    "long_term_count":       0,
    "long_term_history":     [],
    "last_ground_truth_ts":  0.0,
    "ground_truth_count":    0,
}


def read_relationship(owner_name: str) -> str:
    """Read the relationship .md file for owner. Returns empty string if not found."""
    path = os.path.join(RELATIONSHIP_DIR, f"{owner_name.lower()}.md")
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _write_relationship_file(owner_name: str, content: str) -> None:
    """Write the relationship .md file for owner."""
    os.makedirs(RELATIONSHIP_DIR, exist_ok=True)
    path = os.path.join(RELATIONSHIP_DIR, f"{owner_name.lower()}.md")
    with open(path, "w") as f:
        f.write(content)


def _load_relationship_state() -> dict:
    """Load relationship cascading state. Returns defaults if missing."""
    path = os.path.join(RELATIONSHIP_DIR, "state.json")
    try:
        with open(path) as f:
            data = json.load(f)
        # Fill in any missing keys with defaults
        result = dict(_REL_STATE_DEFAULTS)
        result.update(data)
        return result
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_REL_STATE_DEFAULTS)


def _save_relationship_state(rel_state: dict) -> None:
    os.makedirs(RELATIONSHIP_DIR, exist_ok=True)
    path = os.path.join(RELATIONSHIP_DIR, "state.json")
    with open(path, "w") as f:
        json.dump(rel_state, f, indent=2)


def _parse_layer_content(section_text: str) -> Optional[dict]:
    """
    Parse a layer section's prose and scores.
    Returns {"prose": str, "scores": dict} or None if not established.
    """
    if "_Not established yet._" in section_text:
        return None

    prose_lines = []
    for line in section_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("> "):
            prose_lines.append(stripped[2:])
        elif stripped == ">":
            prose_lines.append("")

    prose = "\n".join(prose_lines).strip()

    scores = {}
    for dim in _DIMENSIONS:
        m = re.search(rf"^{dim}:\s*(-?\d+)", section_text, re.MULTILINE)
        if m:
            scores[dim] = max(-2, min(2, int(m.group(1))))

    if not prose and not scores:
        return None

    return {"prose": prose, "scores": scores}


def _read_all_layers(owner_name: str) -> dict:
    """Read all four layers from the relationship .md file."""
    md_content = read_relationship(owner_name)
    layers: dict[str, Optional[dict]] = {}

    for key, label in _LAYER_KEYS:
        header = f"## {label}"
        start = md_content.find(header)
        if start == -1:
            layers[key] = None
            continue
        section_start = start + len(header)
        next_section = md_content.find("\n## ", section_start)
        section_text = (
            md_content[section_start:next_section]
            if next_section != -1
            else md_content[section_start:]
        )
        layers[key] = _parse_layer_content(section_text)

    return layers


def _build_relationship_md(owner_name: str, layers: dict) -> str:
    """Build the full relationship .md file content from layer dicts."""
    display_name = owner_name.capitalize()
    lines = [f"# Relationship — {display_name}", ""]

    for key, label in _LAYER_KEYS:
        lines.append(f"## {label}")
        layer = layers.get(key)
        if not layer:
            lines.append("_Not established yet._")
        else:
            prose = layer.get("prose", "").strip()
            scores = layer.get("scores", {})
            for pl in prose.split("\n"):
                lines.append(f"> {pl}")
            lines.append("")
            for dim in _DIMENSIONS:
                if dim in scores:
                    lines.append(f"{dim}: {scores[dim]}")
        lines.append("")

    return "\n".join(lines)


def _get_net_relationship_dimensions(owner_name: str) -> dict[str, float]:
    """
    Compute the weighted net dimension scores across all present layers.
    Absent layers have their weight redistributed to present layers.
    Returns {dimension: float} in range -2.0 to +2.0.
    """
    layers = _read_all_layers(owner_name)

    layer_scores: dict[str, dict[str, int]] = {}
    for key, _ in _LAYER_KEYS:
        layer = layers.get(key)
        if layer and layer.get("scores"):
            layer_scores[key] = layer["scores"]

    if not layer_scores:
        return {dim: 0.0 for dim in _DIMENSIONS}

    # Renormalize weights to present layers
    total_weight = sum(_LAYER_WEIGHTS[lk] for lk in layer_scores)
    if total_weight <= 0:
        return {dim: 0.0 for dim in _DIMENSIONS}

    net: dict[str, float] = {}
    for dim in _DIMENSIONS:
        weighted_sum = sum(
            layer_scores[lk].get(dim, 0) * _LAYER_WEIGHTS[lk]
            for lk in layer_scores
        )
        net[dim] = round(weighted_sum / total_weight, 3)

    return net


def get_relationship_bond_level(state: BiologicalState, owner_name: str) -> float:
    """
    SPEC-33: Stable bond level blending relationship file (stable across absences)
    with current oxytocin (volatile). Range 0.0–1.0.

    65% from relationship file net bonding so deep history survives multi-day absence;
    35% from live oxytocin so recent warmth still matters.
    """
    net_dims = _get_net_relationship_dimensions(owner_name)
    net_bonding = net_dims.get("bonding", 0.0)  # -2 to +2
    bonding_from_file = (net_bonding + 2.0) / 4.0  # normalize to 0–1
    oxytocin_norm = min(1.0, state.chemicals.get("oxytocin", 4.0) / 40.0)
    return round(0.65 * bonding_from_file + 0.35 * oxytocin_norm, 3)


def _parse_relationship_output(raw: str) -> tuple[str, dict[str, int]]:
    """Parse LLM relationship output: blockquote prose + dimension scores."""
    prose_lines = []
    scores: dict[str, int] = {}

    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("> "):
            prose_lines.append(stripped[2:])
        elif stripped == ">":
            prose_lines.append("")
        else:
            for dim in _DIMENSIONS:
                m = re.match(rf"^{dim}:\s*(-?\d+)$", stripped)
                if m:
                    scores[dim] = max(-2, min(2, int(m.group(1))))

    prose = "\n".join(prose_lines).strip()
    return prose, scores


def _run_relationship_llm(system_prompt: str, user_content: str) -> tuple[str, dict[str, int]]:
    """
    Run an LLM call for a relationship layer write or compaction.
    Returns (prose, scores_dict). Falls back to ("", {}) on failure.
    """
    from src.application.infra.log import log
    try:
        response = chat_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.6,
        )
        from src.application.infra import token_stats
        token_stats.record_response("relationship", response)
        raw = response.choices[0].message.content or ""
        prose, scores = _parse_relationship_output(raw)
        if not prose or not scores:
            log("REL/PARSE", f"Incomplete output — prose={bool(prose)}, scores={len(scores)}")
        return prose, scores
    except Exception as e:
        log("REL/LLM/ERR", str(e))
        return "", {}


_REL_SHORT_TERM_SYSTEM = """\
You are writing Mina's current emotional disposition toward {owner_name}.
This is not a memory log. It is how she feels about him right now, informed by what
just happened between them.

Write 2–4 sentences capturing the emotional texture of the last period: what happened,
how it landed, what tone it leaves her in. Write from inside her experience — not as a
summary of events.

Then assign six dimension scores from -2 to +2 (integers only):
  bonding, security, anticipation, tension, warmth, vigilance

For tension and vigilance: positive score = negative relationship state.
  tension -2 = no conflict; tension +2 = active resentment/hurt
  vigilance -2 = relaxed; vigilance +2 = hypervigilant/walking on eggshells

Your output format (exactly):
> [prose here]

bonding: [score]
security: [score]
anticipation: [score]
tension: [score]
warmth: [score]
vigilance: [score]
"""

_REL_COMPACTION_SYSTEM = """\
You are synthesizing {n} recent {period} entries into a single {layer} view of Mina's
emotional disposition toward {owner_name}.

This is not an average — it is the arc. What has been consistent? What shifted?
What is the emotional chapter this period represents?

Write 2–4 sentences from inside Mina's experience capturing the arc, then assign six
dimension scores from -2 to +2 (integers only):
  bonding, security, anticipation, tension, warmth, vigilance

For tension and vigilance: positive score = negative relationship state.

Your output format (exactly):
> [prose here]

bonding: [score]
security: [score]
anticipation: [score]
tension: [score]
warmth: [score]
vigilance: [score]
"""


def _apply_receptor_sensitivity_changes(
    state: BiologicalState,
    layer_name: str,
    scores: dict[str, int],
) -> BiologicalState:
    """
    SPEC-33: Apply one-time receptor sensitivity changes when long_term or ground_truth
    layers are written. These represent structural adaptation, not acute spikes.
    """
    if layer_name not in ("long_term", "ground_truth"):
        return state

    if "receptor_sensitivity" not in state.__dict__:
        return state

    def _nudge(path1: str, path2: str, delta: float) -> None:
        receptor = state.receptor_sensitivity.setdefault(path1, {})
        receptor[path2] = round(receptor.get(path2, 1.0) + delta, 4)

    bonding  = scores.get("bonding",  0)
    tension  = scores.get("tension",  0)
    security = scores.get("security", 0)

    if bonding >= 1:
        _nudge("oxytocin", "OTR", +0.05)

    if tension >= 1:
        _nudge("cortisol", "GR", -0.05)  # glucocorticoid receptor blunting

    if layer_name == "ground_truth":
        if bonding == 2:
            _nudge("dopamine", "D1", +0.05)

    if layer_name == "long_term":
        if security <= -1:
            _nudge("gaba", "GABA_A", -0.05)

    return state


def consolidate_relationship(state: BiologicalState, owner_name: str) -> BiologicalState:
    """
    SPEC-33: Write the short_term relationship layer and cascade if thresholds met.

    Triggers:
    - When Mina is sleeping (state.sleeping is True)
    - Or when 22h have elapsed since last_short_term_ts

    Reads conversation.jsonl since last_short_term_ts for the short_term write.
    Cascades to medium/long/ground_truth as buffers accumulate.
    Returns state (potentially with updated receptor_sensitivity).
    """
    import time as _time
    from src.application.infra.log import log
    from src.brain.subconscious.decoder import format_state_block

    rel_state = _load_relationship_state()
    now = _time.time()

    last_ts    = rel_state.get("last_short_term_ts", 0.0)
    time_since = now - last_ts
    should_write = state.sleeping or (time_since > 22 * 3600)

    if not should_write:
        return state

    # Read conversation since last short_term write
    conv_entries = _read_conversation_since(last_ts)
    if not conv_entries:
        # No history at all — skip (Open Q #1: don't write empty entry)
        log("REL/SHORT", "No conversation since last write — skipping.")
        return state

    # Format conversation for LLM
    conv_block = _format_conversation_block(conv_entries)

    # Get existing layers for continuity context
    layers = _read_all_layers(owner_name)
    existing_layers_md = read_relationship(owner_name)

    state_block = format_state_block(state)

    system_prompt = _REL_SHORT_TERM_SYSTEM.format(owner_name=owner_name)
    user_content  = "\n\n---\n\n".join([
        state_block,
        f"## Existing relationship layers (for continuity context)\n{existing_layers_md}" if existing_layers_md else "",
        f"## Conversation since last relationship write\n{conv_block}",
    ]).strip()

    log("REL/SHORT", f"Writing short_term for {owner_name} ({len(conv_entries)} conv entries).")
    prose, scores = _run_relationship_llm(system_prompt, user_content)

    if not prose or not scores:
        log("REL/SHORT", "LLM returned empty output — aborting.")
        return state

    # Update short_term layer in .md
    layers["short_term"] = {"prose": prose, "scores": scores}
    _write_relationship_file(owner_name, _build_relationship_md(owner_name, layers))

    # Push to short_term_history buffer for cascading
    rel_state.setdefault("short_term_history", []).append({
        "prose": prose, "scores": scores, "ts": now,
    })
    rel_state["short_term_count"] = rel_state.get("short_term_count", 0) + 1
    rel_state["last_short_term_ts"] = now
    log("REL/SHORT", f"Written. count={rel_state['short_term_count']}")

    # Check cascade: 7 short_term entries → medium_term
    if len(rel_state["short_term_history"]) >= 7:
        state = _compact_relationship_layer(
            state, owner_name, layers, rel_state,
            source_key="short_term", target_key="medium_term",
        )

    _save_relationship_state(rel_state)
    return state


def _compact_relationship_layer(
    state: BiologicalState,
    owner_name: str,
    layers: dict,
    rel_state: dict,
    source_key: str,
    target_key: str,
) -> BiologicalState:
    """
    Compact 7 buffered entries from source layer into a single target layer entry.
    Updates layers dict and rel_state in place. Recursively cascades if target fills.
    """
    import time as _time
    from src.application.infra.log import log

    history_key = f"{source_key}_history"
    count_key   = f"{target_key}_count"
    ts_key      = f"last_{target_key}_ts"

    source_history = rel_state.get(history_key, [])
    if len(source_history) < 7:
        return state

    entries = source_history[:7]

    _period_labels = {
        "short_term":   ("day",  "medium_term"),
        "medium_term":  ("week", "long_term"),
        "long_term":    ("7-week period", "ground_truth"),
    }
    period, _next = _period_labels.get(source_key, ("period", ""))

    system_prompt = _REL_COMPACTION_SYSTEM.format(
        n=len(entries),
        period=period,
        layer=target_key.replace("_", "-"),
        owner_name=owner_name,
    )

    entry_lines = []
    for i, e in enumerate(entries, 1):
        entry_lines.append(f"### Entry {i}\n> {e.get('prose', '')}")
        for dim in _DIMENSIONS:
            if dim in e.get("scores", {}):
                entry_lines.append(f"{dim}: {e['scores'][dim]}")

    user_content = "\n\n".join(entry_lines)

    log("REL/COMPACT", f"{source_key} → {target_key} for {owner_name}")
    prose, scores = _run_relationship_llm(system_prompt, user_content)

    if not prose or not scores:
        log("REL/COMPACT", f"LLM returned empty — aborting {source_key}→{target_key}")
        return state

    # Update target layer in .md
    layers[target_key] = {"prose": prose, "scores": scores}
    _write_relationship_file(owner_name, _build_relationship_md(owner_name, layers))

    # Apply receptor sensitivity changes (long_term and ground_truth only)
    state = _apply_receptor_sensitivity_changes(state, target_key, scores)

    # Push compacted entry to target's history buffer; clear source buffer
    now = _time.time()
    rel_state.setdefault(f"{target_key}_history", []).append(
        {"prose": prose, "scores": scores, "ts": now}
    )
    rel_state[history_key] = source_history[7:]  # consume the 7 used entries
    rel_state[count_key]   = rel_state.get(count_key, 0) + 1
    rel_state[ts_key]      = now

    log("REL/COMPACT", f"{target_key} written. count={rel_state[count_key]}")

    # Cascade further if target buffer reached 7
    _cascade_map = {
        "medium_term": ("medium_term", "long_term"),
        "long_term":   ("long_term",   "ground_truth"),
    }
    if target_key in _cascade_map:
        next_source, next_target = _cascade_map[target_key]
        if len(rel_state.get(f"{next_source}_history", [])) >= 7:
            state = _compact_relationship_layer(
                state, owner_name, layers, rel_state,
                source_key=next_source, target_key=next_target,
            )

    return state
