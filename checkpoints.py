"""
Checkpoint system — snapshot and restore Mina's full runtime state.

A checkpoint captures:
  - state.json          (biological state)
  - conversation.json   (message history)
  - run/monologue.jsonl (inner monologue stream)
  - memory/kag/**/*.md  (accumulated knowledge files)
  - memory/rag/         (ChromaDB episodic memory)

Identity files (identity/MINA.md, identity/APPEARANCE.md) live outside the
memory system entirely and are never touched by any reset command. They are
snapshotted for rollback completeness but never wiped.

Checkpoints live in run/checkpoints/<timestamp>/.
The last MAX_CHECKPOINTS are kept; older ones are pruned automatically.

Reset tiers
-----------
reset()         — Wipe relationship, RAG, knowledge, conversation, monologue.
                  Keeps biomarkers. Identity files untouched (different dir).
factory_reset() — Same as reset() + also resets biomarkers to defaults.
                  Identity files still untouched — factory reset ≠ OS wipe.
"""
import json
import os
import shutil
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_CHECKPOINTS_DIR = os.path.join(_PROJECT_ROOT, "run", "checkpoints")
_MAX_CHECKPOINTS = 48  # ~24h of 30-min heartbeats

# Files/dirs to snapshot (relative to project root)
_SNAPSHOT_FILES = [
    "state.json",
    "conversation.json",
    "run/monologue.md",
]
_SNAPSHOT_DIRS = [
    "identity",      # permanent identity — snapshotted for rollback, never wiped
    "memory/kag",
    "memory/rag",
]


def save(label: str = "heartbeat") -> str:
    """
    Save a checkpoint. Returns the checkpoint directory path.
    label: short string describing what triggered the save (e.g. 'heartbeat', 'manual')
    """
    ts = time.strftime("%Y%m%dT%H%M%S")
    ckpt_dir = os.path.join(_CHECKPOINTS_DIR, f"{ts}_{label}")
    os.makedirs(ckpt_dir, exist_ok=True)

    # Snapshot individual files
    for rel_path in _SNAPSHOT_FILES:
        src = os.path.join(_PROJECT_ROOT, rel_path)
        if os.path.exists(src):
            dst = os.path.join(ckpt_dir, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # Snapshot directories
    for rel_dir in _SNAPSHOT_DIRS:
        src = os.path.join(_PROJECT_ROOT, rel_dir)
        if os.path.exists(src):
            dst = os.path.join(ckpt_dir, rel_dir)
            shutil.copytree(src, dst, dirs_exist_ok=True)

    # Write metadata
    meta = {"ts": time.time(), "label": label, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(ckpt_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    _prune()
    return ckpt_dir


def list_checkpoints() -> list[dict]:
    """
    Return list of available checkpoints, newest first.
    Each dict: {index, dir, created, label, path}
    """
    if not os.path.exists(_CHECKPOINTS_DIR):
        return []
    entries = []
    for name in sorted(os.listdir(_CHECKPOINTS_DIR), reverse=True):
        path = os.path.join(_CHECKPOINTS_DIR, name)
        if not os.path.isdir(path):
            continue
        meta_file = os.path.join(path, "meta.json")
        try:
            with open(meta_file) as f:
                meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {"created": name, "label": "?"}
        entries.append({
            "dir": name,
            "created": meta.get("created", name),
            "label": meta.get("label", "?"),
            "path": path,
        })
    for i, e in enumerate(entries):
        e["index"] = i
    return entries


def restore(index_or_dir: int | str) -> str:
    """
    Restore a checkpoint by index (0 = most recent) or directory name.
    Returns a human-readable summary of what was restored.
    """
    checkpoints = list_checkpoints()
    if not checkpoints:
        raise ValueError("No checkpoints available.")

    if isinstance(index_or_dir, int):
        if index_or_dir >= len(checkpoints):
            raise ValueError(f"Checkpoint {index_or_dir} doesn't exist. Have {len(checkpoints)}.")
        ckpt = checkpoints[index_or_dir]
    else:
        matches = [c for c in checkpoints if c["dir"] == index_or_dir]
        if not matches:
            raise ValueError(f"Checkpoint '{index_or_dir}' not found.")
        ckpt = matches[0]

    ckpt_dir = ckpt["path"]
    restored = []

    # Restore individual files
    for rel_path in _SNAPSHOT_FILES:
        src = os.path.join(ckpt_dir, rel_path)
        if os.path.exists(src):
            dst = os.path.join(_PROJECT_ROOT, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            restored.append(rel_path)

    # Restore directories (full replacement)
    for rel_dir in _SNAPSHOT_DIRS:
        src = os.path.join(ckpt_dir, rel_dir)
        dst = os.path.join(_PROJECT_ROOT, rel_dir)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            restored.append(rel_dir + "/")
        elif os.path.exists(dst):
            # Checkpoint predates RAG tracking — don't wipe existing RAG
            pass

    # Reset in-process RAG cache so it re-reads from the restored directory
    try:
        from memory import _reset_collection
        _reset_collection()
    except Exception:
        pass

    return f"Restored checkpoint '{ckpt['dir']}' ({ckpt['created']}). Files: {', '.join(restored)}"


def _wipe_user_data() -> list[str]:
    """
    Internal: wipe all accumulated user data (conversation, monologue, KAG, RAG).
    Identity files in identity/ are in a completely separate directory — untouched.
    Returns list of wiped items.
    """
    wiped = []

    for rel_path in ["conversation.json", "run/monologue.jsonl"]:
        dst = os.path.join(_PROJECT_ROOT, rel_path)
        if os.path.exists(dst):
            os.remove(dst)
            wiped.append(rel_path)

    # Wipe all KAG files (identity files are in identity/, not here)
    kag_dir = os.path.join(_PROJECT_ROOT, "memory", "kag")
    if os.path.exists(kag_dir):
        for root, dirs, files in os.walk(kag_dir):
            for fname in files:
                full = os.path.join(root, fname)
                os.remove(full)
                wiped.append(os.path.relpath(full, _PROJECT_ROOT).replace(os.sep, "/"))

    # Recreate blank RELATIONSHIP.md
    os.makedirs(kag_dir, exist_ok=True)
    rel_md = os.path.join(kag_dir, "RELATIONSHIP.md")
    with open(rel_md, "w") as f:
        f.write("# Relationship with User\n\nNo history yet.\n")
    wiped.append("memory/kag/RELATIONSHIP.md (reset to blank)")

    # Wipe RAG (ChromaDB episodic memories)
    try:
        from memory import rag_wipe
        rag_wipe()
        wiped.append("memory/rag/ (RAG wiped)")
    except Exception as e:
        wiped.append(f"memory/rag/ (wipe failed: {e})")

    return wiped


def reset() -> str:
    """
    Relationship/memory reset.

    Wipes: conversation, monologue, RAG, all KAG (relationship, knowledge).
    Keeps: biomarkers (state.json). Identity files live in identity/ — untouched.

    A checkpoint is saved first so the wipe is reversible via /rollback.
    """
    ckpt_dir = save(label="pre_reset")
    wiped = _wipe_user_data()

    return (
        f"Reset complete. Checkpoint saved at '{os.path.basename(ckpt_dir)}' (rollback available).\n"
        f"Wiped: {', '.join(wiped)}\n"
        f"Preserved: biomarkers (state.json). Identity files (identity/) untouched."
    )


def factory_reset() -> str:
    """
    Full user-data wipe — like a phone factory reset.

    Wipes everything reset() does, PLUS resets biomarkers to defaults.
    Identity files in identity/ are still untouched — this is not an OS wipe.

    A checkpoint is saved first so the wipe is reversible via /rollback.
    """
    from state import BiologicalState, save_state

    ckpt_dir = save(label="pre_factory_reset")
    wiped = _wipe_user_data()

    # Factory reset also resets biomarkers
    save_state(BiologicalState())
    wiped.append("state.json (biomarkers reset to defaults)")

    return (
        f"Factory reset complete. Checkpoint saved at '{os.path.basename(ckpt_dir)}' (rollback available).\n"
        f"Wiped: {', '.join(wiped)}\n"
        f"Identity files (identity/) untouched."
    )


def _prune() -> None:
    """Remove oldest checkpoints beyond MAX_CHECKPOINTS."""
    checkpoints = list_checkpoints()
    for ckpt in checkpoints[_MAX_CHECKPOINTS:]:
        try:
            shutil.rmtree(ckpt["path"])
        except OSError:
            pass
