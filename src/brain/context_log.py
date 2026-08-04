"""
Last-turn context assembly log — durable, human- and agent-readable.

Writes after each pipeline (and freetime) turn:
  run/last_context.json  — structured record
  run/last_context.md    — plain markdown (cat / read_file friendly)

Also extends turns.jsonl via pipeline with the same assembly fields.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from src.config.config import RUN_DIR
from src.sim.decoder import format_decoder_output

_JSON_PATH = "last_context.json"
_MD_PATH = "last_context.md"


def _paths() -> tuple[Path, Path]:
    root = Path(RUN_DIR)
    return root / _JSON_PATH, root / _MD_PATH


def build_record(
    *,
    ts: float,
    username: str,
    message: str,
    source: str = "chat",
    encoder_output: dict | None = None,
    relationship_modifier: float | None = None,
    decoder_snapshot: dict | None = None,
    big5: dict | None = None,
    window_context: str = "",
    rag_context: str = "",
    kag_context: str = "",
    sliding_result: str = "",
    experiences_result: str = "",
    insula_output: dict | None = None,
    context_output: dict | None = None,
    pfc_output: dict | None = None,
    system_prompt: str = "",
    reply: str = "",
    skipped: bool = False,
    scene: dict | None = None,
) -> dict[str, Any]:
    """Build the canonical assembly record."""
    return {
        "ts": ts,
        "ts_human": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
        "username": username,
        "source": source,
        "message": message,
        "encoder": encoder_output or {},
        "relationship_modifier": relationship_modifier,
        "sim_snapshot": decoder_snapshot or {},
        "big5": big5 or {},
        "assembly": {
            "window_context": window_context or "",
            "rag_context": rag_context or "",
            "kag_context": kag_context or "",
            "sliding_raw": sliding_result or "",
            "experiences_raw": experiences_result or "",
        },
        "insula": insula_output or {},
        "hippocampus": context_output or {},
        "pfc": pfc_output or {},
        "scene": scene or {},
        "system_prompt": system_prompt or "",
        "reply": reply or "",
        "skipped": skipped,
    }


def format_markdown(record: dict[str, Any]) -> str:
    """Render a full assembly dump as readable markdown."""
    lines: list[str] = []
    a = record.get("assembly") or {}

    lines.append("# Mina context assembly")
    lines.append("")
    lines.append(f"- **when:** {record.get('ts_human', '')}")
    lines.append(f"- **source:** {record.get('source', 'chat')}")
    lines.append(f"- **user:** {record.get('username', '')}")
    if record.get("skipped"):
        lines.append("- **skipped reply:** yes (PFC silence)")
    lines.append("")

    lines.append("## User message")
    lines.append("")
    lines.append(_block(record.get("message") or "(empty)"))
    lines.append("")

    lines.append("## Encoder (amygdala)")
    lines.append("")
    lines.append(_kv_block(record.get("encoder") or {}))
    if record.get("relationship_modifier") is not None:
        lines.append(f"- relationship_modifier: {record['relationship_modifier']}")
    lines.append("")

    lines.append("## Decoder (chemistry snapshot)")
    lines.append("")
    snap = record.get("sim_snapshot") or {}
    if snap:
        lines.append("```")
        lines.append(format_decoder_output(snap))
        lines.append("```")
    else:
        lines.append("_(none)_")
    big5 = record.get("big5") or {}
    if big5:
        lines.append("")
        lines.append("**Big 5**")
        lines.append("")
        lines.append(_kv_block(big5))
    lines.append("")

    lines.append("## Context assembly")
    lines.append("")
    lines.append("### Window synthesis")
    lines.append("")
    lines.append(_block(a.get("window_context") or "(none)"))
    lines.append("")
    lines.append("### RAG synthesis")
    lines.append("")
    lines.append(_block(a.get("rag_context") or "(none)"))
    lines.append("")
    lines.append("### KAG")
    lines.append("")
    lines.append(_block(a.get("kag_context") or "(none)"))
    if a.get("sliding_raw") or a.get("experiences_raw"):
        lines.append("")
        lines.append("### Raw retrieval (pre-synthesis)")
        lines.append("")
        if a.get("sliding_raw"):
            lines.append("**Sliding**")
            lines.append("")
            lines.append(_block(a["sliding_raw"]))
            lines.append("")
        if a.get("experiences_raw"):
            lines.append("**Episodic / experiences**")
            lines.append("")
            lines.append(_block(a["experiences_raw"]))
    lines.append("")

    lines.append("## Insula (emotion pillar)")
    lines.append("")
    lines.append(_kv_block(record.get("insula") or {}))
    lines.append("")

    lines.append("## Hippocampus (situation pillar)")
    lines.append("")
    lines.append(_kv_block(record.get("hippocampus") or {}))
    lines.append("")

    lines.append("## PFC (strategy pillar)")
    lines.append("")
    lines.append(_kv_block(record.get("pfc") or {}))
    lines.append("")

    scene = record.get("scene") or {}
    lines.append("## Live scene")
    lines.append("")
    if scene:
        if scene.get("scene_time"):
            lines.append(f"**Now:** {scene['scene_time']}")
            lines.append("")
        if scene.get("timeline"):
            lines.append("**Timeline**")
            for e in scene["timeline"]:
                lines.append(f"- {e.get('when')}: {e.get('what')}")
            lines.append("")
        if scene.get("plans"):
            lines.append("**Plans**")
            for e in scene["plans"]:
                lines.append(f"- {e.get('when')}: {e.get('what')}")
            lines.append("")
        if scene.get("clothing"):
            lines.append("**Clothing**")
            for e in scene["clothing"]:
                lines.append(f"- {e.get('name')}: {e.get('clothing')}")
            lines.append("")
        if scene.get("positions"):
            lines.append("**Positions**")
            for e in scene["positions"]:
                lines.append(f"- {e.get('name')}: {e.get('position')}")
            lines.append("")
    else:
        lines.append("_(none yet)_")
        lines.append("")

    lines.append("## System prompt (what Mina receives)")
    lines.append("")
    sp = (record.get("system_prompt") or "").strip()
    if sp:
        lines.append("```")
        lines.append(sp)
        lines.append("```")
    else:
        lines.append("_(none — e.g. silence skip before prompt build)_")
    lines.append("")

    lines.append("## Reply")
    lines.append("")
    lines.append(_block(record.get("reply") or "(empty / silence)"))
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_last_context(record: dict[str, Any]) -> None:
    """Persist JSON + markdown for the most recent assembly."""
    json_path, md_path = _paths()
    os.makedirs(RUN_DIR, exist_ok=True)
    try:
        json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        md_path.write_text(format_markdown(record))
    except OSError:
        pass


def read_last_context() -> dict[str, Any] | None:
    """Load last_context.json, or rebuild from turns.jsonl tail if missing."""
    json_path, _ = _paths()
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text())
            if isinstance(data, dict) and data:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return _from_turns_tail()


def read_last_context_markdown() -> str:
    """Prefer last_context.md; else format from JSON/turns."""
    _, md_path = _paths()
    if md_path.exists():
        try:
            text = md_path.read_text()
            if text.strip():
                return text
        except OSError:
            pass
    record = read_last_context()
    if not record:
        return "# Mina context assembly\n\n_(no turns yet)_\n"
    return format_markdown(record)


def _from_turns_tail() -> dict[str, Any] | None:
    """Best-effort load from turns.jsonl for pre-existing turns without last_context.*."""
    path = Path(RUN_DIR) / "turns.jsonl"
    if not path.exists():
        return None
    try:
        # Read last non-empty line without loading the whole file into memory
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return None
            chunk = min(size, 256_000)
            f.seek(-chunk, os.SEEK_END)
            data = f.read().decode("utf-8", errors="replace")
        line = ""
        for candidate in reversed(data.splitlines()):
            if candidate.strip():
                line = candidate.strip()
                break
        if not line:
            return None
        turn = json.loads(line)
    except (OSError, json.JSONDecodeError):
        return None

    assembly = turn.get("assembly") or {
        "window_context": turn.get("window_context", ""),
        "rag_context": turn.get("rag_context", ""),
        "kag_context": turn.get("kag_context", ""),
        "sliding_raw": turn.get("sliding_raw", ""),
        "experiences_raw": turn.get("experiences_raw", ""),
    }
    return {
        "ts": turn.get("ts"),
        "ts_human": turn.get("ts_human", ""),
        "username": turn.get("username", ""),
        "source": turn.get("source", "chat"),
        "message": turn.get("message", ""),
        "encoder": turn.get("encoder") or {},
        "relationship_modifier": turn.get("relationship_modifier"),
        "sim_snapshot": turn.get("sim_snapshot") or {},
        "big5": turn.get("big5") or {},
        "assembly": assembly,
        "insula": turn.get("insula") or {},
        "hippocampus": turn.get("hippocampus") or {},
        "pfc": turn.get("pfc") or {},
        "system_prompt": turn.get("system_prompt", ""),
        "reply": turn.get("reply", ""),
        "skipped": bool(turn.get("skipped", False)),
    }


def _block(text: str) -> str:
    text = str(text).strip()
    if not text:
        return "_(empty)_"
    # Indent so markdown lists/headers inside content don't break structure
    return "\n".join(f"    {line}" if line else "" for line in text.splitlines())


def _kv_block(d: dict) -> str:
    if not d:
        return "_(none)_"
    lines = []
    for k, v in d.items():
        if v is None or v == "":
            lines.append(f"- **{k}:** _(none)_")
        elif isinstance(v, (dict, list)):
            lines.append(f"- **{k}:** `{json.dumps(v, ensure_ascii=False)}`")
        else:
            # Multi-line values
            s = str(v)
            if "\n" in s:
                lines.append(f"- **{k}:**")
                lines.append("")
                lines.append(_block(s))
            else:
                lines.append(f"- **{k}:** {s}")
    return "\n".join(lines)
