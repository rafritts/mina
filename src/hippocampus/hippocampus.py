"""
Hippocampus — long-term memory and consolidation.

Ported from v1 with minimal changes:
  - Path imports updated to v2 config
  - BiologicalState dependency removed (v2 uses ChemicalState)
  - consolidate() updated to not require BiologicalState
  - consolidate_relationship() simplified (receptor sensitivity changes deferred to v3)

Storage layout:
  identity/                — permanent identity files (MINA.md). Never wiped.
  memory/kag/              — accumulated knowledge files. Wiped on reset.
  memory/rag/              — ChromaDB episodic memory. Wiped on reset.
  memory/relationships/    — per-person relationship markdown files.
"""
import json
import os
import re
import threading
import time
from typing import Optional

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import (
    MODEL, CONTEXT_MODEL,
    IDENTITY_DIR, KAG_DIR, RAG_DIR, RELATIONSHIP_DIR,
    CONSOLIDATION_STATE_FILE, SLIDING_SEQ_FILE,
    get_conversation_file, RUN_DIR,
)

_SLIDING_WINDOW = 10

# ── ChromaDB lazy init ─────────────────────────────────────────────────────────

_chroma_lock        = threading.Lock()
_chroma_client      = None
_collection         = None
_sliding_collection = None

OLLAMA_EMBED_MODEL = "embeddinggemma:latest"
OLLAMA_BASE_URL    = "http://localhost:11434"


# ── Identity ─────────────────────────────────────────────────────────────────

def read_identity(filename: str) -> str:
    path = os.path.join(IDENTITY_DIR, filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ── KAG — file-based knowledge ───────────────────────────────────────────────

def read_kag(filename: str) -> str:
    path = os.path.join(KAG_DIR, filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_kag(filename: str, content: str) -> None:
    os.makedirs(KAG_DIR, exist_ok=True)
    path = os.path.join(KAG_DIR, filename)
    with open(path, "w") as f:
        f.write(content)


def list_knowledge() -> list[str]:
    knowledge_dir = os.path.join(KAG_DIR, "KNOWLEDGE")
    if not os.path.isdir(knowledge_dir):
        return []
    return [f for f in os.listdir(knowledge_dir) if f.endswith(".md")]


def read_knowledge(filename: str) -> str:
    path = os.path.join(KAG_DIR, "KNOWLEDGE", filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_knowledge(filename: str, content: str) -> None:
    knowledge_dir = os.path.join(KAG_DIR, "KNOWLEDGE")
    os.makedirs(knowledge_dir, exist_ok=True)
    with open(os.path.join(knowledge_dir, filename), "w") as f:
        f.write(content)


def _select_knowledge_files(stimulus: str, fnames: list[str]) -> list[str]:
    if not fnames:
        return []
    if not stimulus:
        return fnames

    candidates = []
    for fname in fnames:
        content = read_knowledge(fname)
        if content:
            candidates.append(f"=== {fname} ===\n{content}")
    if not candidates:
        return []

    prompt = (
        f"Current stimulus:\n{stimulus}\n\n"
        f"Knowledge files — return ONLY a JSON array of relevant filenames:\n\n"
        + "\n\n".join(candidates)
    )
    try:
        resp = chat_create(
            model=CONTEXT_MODEL,
            messages=[
                {"role": "system", "content":
                    "Return a JSON array of filenames relevant to the stimulus. Raw JSON only."},
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
    return fnames


def build_kag_context(query: str = "") -> str:
    parts = []

    mina = read_identity("MINA.md")
    if mina:
        parts.append(f"## Character\n{mina}")

    if os.path.exists(RELATIONSHIP_DIR):
        for fn in sorted(os.listdir(RELATIONSHIP_DIR)):
            if not fn.endswith(".md"):
                continue
            person  = fn[:-3]
            content = read_relationship(person)
            if content:
                parts.append(f"## Relationship with {person.capitalize()}\n{content}")

    reflection = read_kag("REFLECTION.md")
    if reflection:
        parts.append(f"## Reflection\n{reflection}")

    knowledge_files = list_knowledge()
    selected = _select_knowledge_files(query, knowledge_files)
    for fname in selected:
        content = read_knowledge(fname)
        if content:
            parts.append(f"## Knowledge: {fname}\n{content}")

    return "\n\n---\n\n".join(parts)


# ── RAG — ChromaDB episodic memory ───────────────────────────────────────────

class _OllamaEmbeddingFunction:
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
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        result = _json.loads(resp.read())
                    embeddings.append(result["embedding"])
                    break
                except urllib.error.HTTPError as e:
                    if e.code < 500:
                        raise
                    time.sleep(1.0 * (attempt + 1))
        return embeddings

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)


def _init_chroma_locked() -> None:
    global _chroma_client, _collection
    if _chroma_client is not None:
        return
    try:
        import chromadb
    except ImportError:
        return
    os.makedirs(RAG_DIR, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=RAG_DIR)
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
        if _collection is None:
            _init_chroma_locked()
    return _collection


def _reset_collection() -> None:
    global _chroma_client, _collection
    _chroma_client = None
    _collection = None


def _get_sliding_collection():
    global _sliding_collection
    if _sliding_collection is not None:
        return _sliding_collection
    with _chroma_lock:
        if _sliding_collection is not None:
            return _sliding_collection
        if _chroma_client is None:
            _init_chroma_locked()
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


def sliding_rag_wipe() -> None:
    """
    Drop short-term sliding conversation memory only.
    Keeps episodic RAG (experiences) and KAG knowledge.
    """
    global _chroma_client, _sliding_collection
    with _chroma_lock:
        try:
            if _chroma_client is None and os.path.exists(RAG_DIR):
                _init_chroma_locked()
            if _chroma_client is not None:
                try:
                    _chroma_client.delete_collection("mina_sliding")
                except Exception:
                    pass
        finally:
            _sliding_collection = None
    try:
        os.remove(SLIDING_SEQ_FILE)
    except FileNotFoundError:
        pass


def rag_wipe() -> None:
    import shutil
    _reset_collection()
    _reset_sliding_collection()
    if os.path.exists(RAG_DIR):
        shutil.rmtree(RAG_DIR)
    try:
        os.remove(SLIDING_SEQ_FILE)
    except FileNotFoundError:
        pass


def rag_add(text: str, metadata: Optional[dict] = None) -> None:
    collection = _get_collection()
    if collection is None:
        return
    doc_id = f"exp_{int(time.time() * 1000)}"
    meta   = {"timestamp": time.time()}
    if metadata:
        meta.update(metadata)
    try:
        collection.add(documents=[text], ids=[doc_id], metadatas=[meta])
    except Exception as e:
        if "does not exist" in str(e):
            _reset_collection()
        log("RAG/ADD/ERR", str(e))


_RAG_HALF_LIFE_RECENT_HOURS    = 0.33
_RAG_HALF_LIFE_HISTORY_HOURS   = 48.0
_RAG_HALF_LIFE_RELATIONAL_HOURS = 720.0
_RAG_SIMILARITY_FLOOR          = 0.75


def _rag_query_with_half_life(query: str, n_results: int, half_life_hours: float) -> list[str]:
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
            similarity = 1.0 - dist
            if similarity < _RAG_SIMILARITY_FLOOR:
                continue
            age_s = now - float((meta or {}).get("timestamp", now))
            decay = 0.5 ** (age_s / half_life_s)
            scored.append((similarity * decay, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        deduped = []
        for _, doc in scored:
            if doc not in seen:
                seen.add(doc)
                deduped.append(doc)
        return deduped[:n_results]
    except Exception as e:
        if "does not exist" in str(e):
            _reset_collection()
        return []


def build_rag_context_dual(query: str, n_results: int = 4) -> tuple[str, str]:
    recent_docs  = _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_RECENT_HOURS)
    history_docs = _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_HISTORY_HOURS)
    recent_set   = set(recent_docs)
    history_docs = [d for d in history_docs if d not in recent_set]
    recent_str  = "\n".join(f"- {m}" for m in recent_docs)  if recent_docs  else ""
    history_str = "\n".join(f"- {m}" for m in history_docs) if history_docs else ""
    return recent_str, history_str


def build_rag_context_relational(query: str, n_results: int = 3) -> str:
    docs = _rag_query_with_half_life(query, n_results, _RAG_HALF_LIFE_RELATIONAL_HOURS)
    if not docs:
        return ""
    return "\n".join(f"- {d}" for d in docs)


# ── Sliding window RAG ────────────────────────────────────────────────────────

def _load_sliding_seq() -> int:
    try:
        with open(SLIDING_SEQ_FILE) as f:
            return int(json.load(f).get("seq", 0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 0


def _save_sliding_seq(seq: int) -> None:
    os.makedirs(os.path.dirname(SLIDING_SEQ_FILE), exist_ok=True)
    with open(SLIDING_SEQ_FILE, "w") as f:
        json.dump({"seq": seq}, f)


def sliding_rag_write(decoder_window: list[dict]) -> None:
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
    ]
    if not conv_entries:
        return
    window = conv_entries[-_SLIDING_WINDOW:]
    block  = _format_conversation_block(window)
    if not block:
        return
    seq = _load_sliding_seq() + 1
    _save_sliding_seq(seq)
    chunk_ts = next((e["ts"] for e in reversed(window) if e.get("ts")), time.time())
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


def sliding_rag_query(query: str, expand_radius: int = 3) -> str:
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
            include=["documents", "metadatas", "distances"],
        )
        docs      = results.get("documents", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        if not docs:
            return ""
        if (1.0 - distances[0]) < _RAG_SIMILARITY_FLOOR:
            return ""
        match_seq = int((metas[0] or {}).get("seq", 0))
        match_doc = docs[0]
        expand_seqs = [match_seq + i for i in range(-expand_radius, expand_radius + 1) if i != 0]
        try:
            adj = collection.get(
                where={"seq": {"$in": expand_seqs}},
                include=["documents", "metadatas"],
            )
            adj_docs  = adj.get("documents") or []
            adj_metas = adj.get("metadatas") or []
        except Exception:
            adj_docs, adj_metas = [], []
        all_chunks = [(match_seq, match_doc)]
        for doc, meta in zip(adj_docs, adj_metas):
            all_chunks.append((int((meta or {}).get("seq", 0)), doc))
        all_chunks.sort(key=lambda x: x[0])
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
    global _sliding_collection
    if _chroma_client is not None:
        try:
            _chroma_client.delete_collection("mina_sliding")
        except Exception:
            pass
    _reset_sliding_collection()
    try:
        os.remove(SLIDING_SEQ_FILE)
    except FileNotFoundError:
        pass


# ── Conversation log reading ──────────────────────────────────────────────────

def _read_conversation_since(since_ts: float) -> list[dict]:
    import glob as _glob
    pattern = os.path.join(RUN_DIR, "conversation-*.jsonl")
    files   = sorted(_glob.glob(pattern))
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
    from src.brain.stage_direction import visible_speech

    lines = []
    for e in entries:
        role    = e.get("role", "?")
        content = e.get("content", "")
        ts      = e.get("ts")
        if not content:
            continue
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if role == "user":
            spoken = visible_speech(content)
            if not spoken:
                continue
            content = spoken
        content = str(content).strip()[:400]
        if not content:
            continue
        label = "USER" if role == "user" else "MINA"
        if ts:
            delta = time.time() - ts
            age   = (f"{int(delta/60)}m ago" if delta < 3600
                     else f"{int(delta/3600)}h ago" if delta < 86400
                     else f"{int(delta/86400)}d ago")
            lines.append(f"[{age}] {label}: {content}")
        else:
            lines.append(f"{label}: {content}")
    return "\n".join(lines)


# ── Consolidation ─────────────────────────────────────────────────────────────

_CONSOLIDATION_SYSTEM = """\
You are the subconscious of an AI named Mina, running in reflection mode.

You are called during freetime — a scheduled autonomous cycle. Consolidate what \
has happened since the last reflection into long-term memory.

## Output format

<reflection_summary>
[1-3 sentences: what happened, what mattered, what shifted]
</reflection_summary>
<rag_entries>
[{"text": "...", "metadata": {"type": "episodic", "importance": "high|medium|low"}}]
</rag_entries>
<kag_updates>
{
  "PENDING.md": "[updated content or null]",
  "REFLECTION.md": "[new diary entry to append, or null]",
  "KNOWLEDGE/<filename>.md": "[content or null]"
}
</kag_updates>
<followups>
[{"context": "...", "delay_minutes": 60}]
</followups>

REFLECTION.md is Mina's private diary — first person, what she actually thinks and \
feels about what happened. Not a summary. What it left in her. If nothing shifted, null.
RAG entries: specific meaningful moments, not summaries.
"""


def _extract_tag(raw: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", raw, re.DOTALL)
    return m.group(1).strip() if m else ""


def _parse_json_robust(text: str):
    text = text.strip()
    if not text:
        return None
    opener = text[0]
    if opener not in ("{", "["):
        for i, ch in enumerate(text):
            if ch in ("{", "["):
                text = text[i:]
                opener = ch
                break
        else:
            return None
    closer = "]" if opener == "[" else "}"
    depth, in_string, escape = 0, False, False
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
                    return json.loads(text[:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def consolidate(kag_context: str) -> dict:
    con_state  = _load_consolidation_state()
    since_ts   = con_state.get("last_consolidated_ts", 0.0)
    new_entries = _read_conversation_since(since_ts)

    history_lines = []
    for entry in new_entries:
        role    = entry.get("role", "?")
        content = entry.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        history_lines.append(f"{role.upper()}: {str(content)[:500]}")

    user_content = "\n\n---\n\n".join([
        kag_context,
        "## Conversation Since Last Consolidation\n" + (
            "\n".join(history_lines) if history_lines else "(nothing new)"
        ),
    ])

    response = chat_create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _CONSOLIDATION_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.5,
    )
    raw    = response.choices[0].message.content or ""
    result = {
        "reflection_summary": _extract_tag(raw, "reflection_summary"),
        "rag_entries": [],
        "kag_updates": {},
        "followups": [],
    }
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

    _save_consolidation_state({"last_consolidated_ts": time.time()})
    return result


# ── Relationship memory ───────────────────────────────────────────────────────

_DIMENSIONS  = ["bonding", "security", "anticipation", "tension", "warmth", "vigilance"]
_LAYER_KEYS  = [
    ("ground_truth", "Ground Truth"),
    ("long_term",    "Long-Term View"),
    ("medium_term",  "Medium-Term View"),
    ("short_term",   "Short-Term View"),
]
_LAYER_WEIGHTS = {"ground_truth": 0.40, "long_term": 0.30, "medium_term": 0.20, "short_term": 0.10}

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
    path = os.path.join(RELATIONSHIP_DIR, f"{owner_name.lower()}.md")
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _write_relationship_file(owner_name: str, content: str) -> None:
    os.makedirs(RELATIONSHIP_DIR, exist_ok=True)
    path = os.path.join(RELATIONSHIP_DIR, f"{owner_name.lower()}.md")
    with open(path, "w") as f:
        f.write(content)


def _load_relationship_state() -> dict:
    path = os.path.join(RELATIONSHIP_DIR, "state.json")
    try:
        with open(path) as f:
            data = json.load(f)
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
    if "_Not established yet._" in section_text:
        return None
    prose_lines = []
    for line in section_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("> "):
            prose_lines.append(stripped[2:])
        elif stripped == ">":
            prose_lines.append("")
    prose  = "\n".join(prose_lines).strip()
    scores = {}
    for dim in _DIMENSIONS:
        m = re.search(rf"^{dim}:\s*(-?\d+)", section_text, re.MULTILINE)
        if m:
            scores[dim] = max(-2, min(2, int(m.group(1))))
    if not prose and not scores:
        return None
    return {"prose": prose, "scores": scores}


def _read_all_layers(owner_name: str) -> dict:
    md_content = read_relationship(owner_name)
    layers: dict[str, Optional[dict]] = {}
    for key, label in _LAYER_KEYS:
        header = f"## {label}"
        start  = md_content.find(header)
        if start == -1:
            layers[key] = None
            continue
        section_start = start + len(header)
        next_section  = md_content.find("\n## ", section_start)
        section_text  = (md_content[section_start:next_section] if next_section != -1
                         else md_content[section_start:])
        layers[key] = _parse_layer_content(section_text)
    return layers


def _build_relationship_md(owner_name: str, layers: dict) -> str:
    lines = [f"# Relationship — {owner_name.capitalize()}", ""]
    for key, label in _LAYER_KEYS:
        lines.append(f"## {label}")
        layer = layers.get(key)
        if not layer:
            lines.append("_Not established yet._")
        else:
            for pl in layer.get("prose", "").strip().split("\n"):
                lines.append(f"> {pl}")
            lines.append("")
            for dim in _DIMENSIONS:
                if dim in layer.get("scores", {}):
                    lines.append(f"{dim}: {layer['scores'][dim]}")
        lines.append("")
    return "\n".join(lines)


def _get_net_relationship_dimensions(owner_name: str) -> dict[str, float]:
    layers = _read_all_layers(owner_name)
    layer_scores = {k: layers[k]["scores"] for k, _ in _LAYER_KEYS
                    if layers.get(k) and layers[k].get("scores")}
    if not layer_scores:
        return {dim: 0.0 for dim in _DIMENSIONS}
    total_weight = sum(_LAYER_WEIGHTS[lk] for lk in layer_scores)
    if total_weight <= 0:
        return {dim: 0.0 for dim in _DIMENSIONS}
    net: dict[str, float] = {}
    for dim in _DIMENSIONS:
        weighted_sum = sum(layer_scores[lk].get(dim, 0) * _LAYER_WEIGHTS[lk]
                           for lk in layer_scores)
        net[dim] = round(weighted_sum / total_weight, 3)
    return net


def get_relationship_modifier(owner_name: str) -> float:
    """
    Return a 0.1–1.0 chemistry multiplier for this person.

    Stranger (no relationship file / no layers): 0.1
    As bonding, warmth, and security accumulate across layers, modifier rises.
    At maximum positive scores on all three dimensions: 1.0.

    This is the gate that prevents a first conversation from producing
    relationship-level chemistry effects regardless of conversation content.
    """
    dims = _get_net_relationship_dimensions(owner_name)

    # If all dims are 0.0 there are no layers yet — true stranger
    if all(v == 0.0 for v in dims.values()):
        return 0.1

    # Primary trust signal: bonding + warmth + security (each -2 to +2, so sum -6 to +6)
    trust = dims.get("bonding", 0.0) + dims.get("warmth", 0.0) + dims.get("security", 0.0)

    # Map -6..+6 → 0.1..1.0
    # At trust=0 (neutral acquaintance): ~0.4
    # At trust=+6 (maximum): 1.0
    # At trust=-6 (actively hostile): 0.1
    modifier = 0.1 + (trust + 6.0) / 12.0 * 0.9
    return round(max(0.1, min(1.0, modifier)), 3)


def _parse_relationship_output(raw: str) -> tuple[str, dict[str, int]]:
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
    return "\n".join(prose_lines).strip(), scores


def _run_relationship_llm(system_prompt: str, user_content: str) -> tuple[str, dict[str, int]]:
    try:
        response = chat_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.6,
        )
        raw = response.choices[0].message.content or ""
        return _parse_relationship_output(raw)
    except Exception as e:
        log("REL/LLM/ERR", str(e))
        return "", {}


_REL_SHORT_TERM_SYSTEM = """\
You are writing Mina's current emotional disposition toward {owner_name}.
Write 2-4 sentences from inside her experience. Then assign six dimension scores (-2 to +2):
  bonding, security, anticipation, tension, warmth, vigilance

tension/vigilance: positive = negative state.

Format:
> [prose]

bonding: [score]
security: [score]
anticipation: [score]
tension: [score]
warmth: [score]
vigilance: [score]
"""

_REL_COMPACTION_SYSTEM = """\
Synthesize {n} {period} entries into a single {layer} view of Mina's disposition toward {owner_name}.
Write the arc — what's consistent, what shifted. 2-4 sentences + six dimension scores.
Same format: blockquote prose + score lines.
"""


def consolidate_relationship(owner_name: str, sleeping: bool = False) -> None:
    rel_state  = _load_relationship_state()
    now        = time.time()
    last_ts    = rel_state.get("last_short_term_ts", 0.0)
    time_since = now - last_ts

    if not sleeping and time_since < 22 * 3600:
        return

    conv_entries = _read_conversation_since(last_ts)
    if not conv_entries:
        return

    conv_block      = _format_conversation_block(conv_entries)
    existing_layers = read_relationship(owner_name)
    layers          = _read_all_layers(owner_name)

    system_prompt = _REL_SHORT_TERM_SYSTEM.format(owner_name=owner_name)
    user_content  = "\n\n---\n\n".join(filter(None, [
        f"## Existing layers\n{existing_layers}" if existing_layers else "",
        f"## Conversation\n{conv_block}",
    ]))

    prose, scores = _run_relationship_llm(system_prompt, user_content)
    if not prose or not scores:
        return

    layers["short_term"] = {"prose": prose, "scores": scores}
    _write_relationship_file(owner_name, _build_relationship_md(owner_name, layers))

    rel_state.setdefault("short_term_history", []).append({"prose": prose, "scores": scores, "ts": now})
    rel_state["short_term_count"]  = rel_state.get("short_term_count", 0) + 1
    rel_state["last_short_term_ts"] = now

    if len(rel_state["short_term_history"]) >= 7:
        _compact_layer(owner_name, layers, rel_state, "short_term", "medium_term")

    _save_relationship_state(rel_state)


def _compact_layer(owner_name, layers, rel_state, source_key, target_key):
    history_key = f"{source_key}_history"
    source_history = rel_state.get(history_key, [])
    if len(source_history) < 7:
        return

    entries = source_history[:7]
    _period_labels = {
        "short_term":  ("day",       "medium_term"),
        "medium_term": ("week",      "long_term"),
        "long_term":   ("7-week period", "ground_truth"),
    }
    period, _ = _period_labels.get(source_key, ("period", ""))

    system_prompt = _REL_COMPACTION_SYSTEM.format(
        n=len(entries), period=period,
        layer=target_key.replace("_", "-"), owner_name=owner_name,
    )
    entry_lines = []
    for i, e in enumerate(entries, 1):
        entry_lines.append(f"### Entry {i}\n> {e.get('prose','')}")
        for dim in _DIMENSIONS:
            if dim in e.get("scores", {}):
                entry_lines.append(f"{dim}: {e['scores'][dim]}")
    user_content = "\n\n".join(entry_lines)

    prose, scores = _run_relationship_llm(system_prompt, user_content)
    if not prose or not scores:
        return

    layers[target_key] = {"prose": prose, "scores": scores}
    _write_relationship_file(owner_name, _build_relationship_md(owner_name, layers))

    now = time.time()
    rel_state.setdefault(f"{target_key}_history", []).append({"prose": prose, "scores": scores, "ts": now})
    rel_state[history_key] = source_history[7:]
    rel_state[f"{target_key}_count"] = rel_state.get(f"{target_key}_count", 0) + 1
    rel_state[f"last_{target_key}_ts"] = now

    _cascade_map = {"medium_term": ("medium_term", "long_term"), "long_term": ("long_term", "ground_truth")}
    if target_key in _cascade_map:
        ns, nt = _cascade_map[target_key]
        if len(rel_state.get(f"{ns}_history", [])) >= 7:
            _compact_layer(owner_name, layers, rel_state, ns, nt)
