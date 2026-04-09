"""
Checkpoint system — snapshot and restore Mina's full runtime state.

A checkpoint captures:
  - state.json          (biological state)
  - conversation.json   (message history)
  - run/monologue.jsonl (inner monologue stream)
  - memory/kag/**/*.md  (all KAG knowledge files)

Checkpoints live in run/checkpoints/<timestamp>/.
The last MAX_CHECKPOINTS are kept; older ones are pruned automatically.
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
    "run/monologue.jsonl",
]
_SNAPSHOT_DIRS = [
    "memory/kag",
]

# Files preserved on full reset (her core identity, not accumulated memory)
_RESET_PRESERVE = {
    "memory/kag/MINA.md",
    "memory/kag/APPEARANCE.md",
    "memory/kag/PENDING.md",
}


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

    # Restore directories
    for rel_dir in _SNAPSHOT_DIRS:
        src = os.path.join(ckpt_dir, rel_dir)
        if os.path.exists(src):
            dst = os.path.join(_PROJECT_ROOT, rel_dir)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            restored.append(rel_dir + "/")

    return f"Restored checkpoint '{ckpt['dir']}' ({ckpt['created']}). Files: {', '.join(restored)}"


def reset() -> str:
    """
    Full reset: save a checkpoint first, then wipe accumulated state.
    Preserves MINA.md, APPEARANCE.md, PENDING.md (her identity, not her memory).
    Returns summary.
    """
    # Save a checkpoint before wiping so it's reversible
    ckpt_dir = save(label="pre_reset")

    wiped = []

    # Clear runtime files
    for rel_path in _SNAPSHOT_FILES:
        dst = os.path.join(_PROJECT_ROOT, rel_path)
        if os.path.exists(dst):
            os.remove(dst)
            wiped.append(rel_path)

    # Clear KAG files except preserved ones
    kag_dir = os.path.join(_PROJECT_ROOT, "memory", "kag")
    for root, dirs, files in os.walk(kag_dir):
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, _PROJECT_ROOT).replace(os.sep, "/")
            if rel not in _RESET_PRESERVE:
                os.remove(full)
                wiped.append(rel)

    # Reset RELATIONSHIP.md to blank slate
    rel_md = os.path.join(_PROJECT_ROOT, "memory", "kag", "RELATIONSHIP.md")
    with open(rel_md, "w") as f:
        f.write("# Relationship with User\n\nNo history yet.\n")
    wiped.append("memory/kag/RELATIONSHIP.md (reset)")

    return (
        f"Reset complete. Checkpoint saved at '{os.path.basename(ckpt_dir)}' (rollback available).\n"
        f"Wiped: {', '.join(wiped)}"
    )


def factory_reset() -> str:
    """
    Nuclear option: wipe absolutely everything including MINA.md and APPEARANCE.md.
    Resets biomarkers to default BiologicalState. A checkpoint is saved first.
    """
    from state import BiologicalState, save_state

    ckpt_dir = save(label="pre_factory_reset")
    wiped = []

    # Clear all runtime files
    for rel_path in _SNAPSHOT_FILES:
        dst = os.path.join(_PROJECT_ROOT, rel_path)
        if os.path.exists(dst):
            os.remove(dst)
            wiped.append(rel_path)

    # Wipe entire KAG directory
    kag_dir = os.path.join(_PROJECT_ROOT, "memory", "kag")
    if os.path.exists(kag_dir):
        shutil.rmtree(kag_dir)
        os.makedirs(kag_dir, exist_ok=True)
        wiped.append("memory/kag/ (all files)")

    # Reset biomarkers to defaults
    save_state(BiologicalState())
    wiped.append("state.json (biomarkers reset to default)")

    return (
        f"Factory reset complete. Checkpoint saved at '{os.path.basename(ckpt_dir)}'.\n"
        f"Wiped: {', '.join(wiped)}"
    )


def _prune() -> None:
    """Remove oldest checkpoints beyond MAX_CHECKPOINTS."""
    checkpoints = list_checkpoints()
    for ckpt in checkpoints[_MAX_CHECKPOINTS:]:
        try:
            shutil.rmtree(ckpt["path"])
        except OSError:
            pass
