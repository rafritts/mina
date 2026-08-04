"""
Live scene context — agent-authored short-term coherence (Kaiya pattern).

Mouth emits scene fields in its JSON reply body each turn. Host stores them
in run/scene_context.json and re-injects prior state next turn into:
  - hippocampus (Context pillar)
  - PFC
  - mouth system prompt

Host never invents clothing/positions/time — only stores and re-injects.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from src.config.config import RUN_DIR

SCENE_FILE = os.path.join(RUN_DIR, "scene_context.json")
SCENE_TIMELINE_MAX = 12
SCENE_PLANS_MAX = 6

_EMPTY = {
    "clothing": [],
    "positions": [],
    "scene_time": "",
    "timeline": [],
    "plans": [],
    "updated_at": 0.0,
}


def empty_scene() -> dict:
    return {
        "clothing": [],
        "positions": [],
        "scene_time": "",
        "timeline": [],
        "plans": [],
        "updated_at": 0.0,
    }


def scene_has_content(sc: dict | None) -> bool:
    if not sc:
        return False
    return bool(
        sc.get("clothing")
        or sc.get("positions")
        or (sc.get("scene_time") or "").strip()
        or sc.get("timeline")
        or sc.get("plans")
    )


def load_scene() -> dict:
    try:
        with open(SCENE_FILE) as f:
            raw = json.load(f)
        return sanitize_scene(raw) or empty_scene()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return empty_scene()


def save_scene(sc: dict) -> None:
    clean = sanitize_scene(sc)
    if clean is None:
        clear_scene()
        return
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(SCENE_FILE, "w") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
        f.write("\n")


def clear_scene() -> None:
    try:
        if os.path.exists(SCENE_FILE):
            os.unlink(SCENE_FILE)
    except OSError:
        pass


def _cap_timeline(entries: list[dict]) -> list[dict]:
    if len(entries) <= SCENE_TIMELINE_MAX:
        return entries
    return entries[-SCENE_TIMELINE_MAX:]


def _cap_plans(entries: list[dict]) -> list[dict]:
    if len(entries) <= SCENE_PLANS_MAX:
        return entries
    return entries[:SCENE_PLANS_MAX]


def sanitize_scene(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None

    clothing: list[dict] = []
    for item in raw.get("clothing") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        clothing_text = str(item.get("clothing") or "").strip()
        if name and clothing_text:
            clothing.append({"name": name, "clothing": clothing_text})

    positions: list[dict] = []
    for item in raw.get("positions") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        position = str(item.get("position") or "").strip()
        if name and position:
            positions.append({"name": name, "position": position})

    scene_time = str(raw.get("scene_time") or raw.get("sceneTime") or "").strip()

    timeline: list[dict] = []
    for item in raw.get("timeline") or []:
        if not isinstance(item, dict):
            continue
        when = str(item.get("when") or "").strip()
        what = str(item.get("what") or "").strip()
        if when and what:
            timeline.append({"when": when, "what": what})

    plans: list[dict] = []
    for item in raw.get("plans") or []:
        if not isinstance(item, dict):
            continue
        when = str(item.get("when") or "").strip()
        what = str(item.get("what") or "").strip()
        if when and what:
            plans.append({"when": when, "what": what})

    if not (clothing or positions or scene_time or timeline or plans):
        return None

    updated = raw.get("updated_at") or raw.get("updatedAt") or time.time()
    try:
        updated_at = float(updated)
    except (TypeError, ValueError):
        updated_at = time.time()

    return {
        "clothing": clothing,
        "positions": positions,
        "scene_time": scene_time,
        "timeline": _cap_timeline(timeline),
        "plans": _cap_plans(plans),
        "updated_at": updated_at,
    }


def scene_fields_from_mouth(data: dict) -> dict:
    """
    Extract scene fields from a mouth JSON object (wire keys).
    Returns a partial dict suitable for apply_scene_from_mouth.
    """
    clothing_raw = data.get("current_clothing_scene_members")
    positions_raw = data.get("current_position_in_scene")
    scene_time = data.get("scene_time")
    timeline_raw = data.get("timeline")
    plans_raw = data.get("plans")

    out: dict[str, Any] = {}
    if clothing_raw is not None:
        out["clothing"] = clothing_raw
    if positions_raw is not None:
        out["positions"] = positions_raw
    if scene_time is not None:
        out["scene_time"] = scene_time
    if timeline_raw is not None:
        out["timeline"] = timeline_raw
    if "plans" in data:
        out["plans"] = plans_raw
    return out


def apply_scene_from_mouth(prev: dict | None, mouth_fields: dict) -> dict | None:
    """
    Merge mouth scene fields into host scene.

    Clothing/positions: present keys replace that dimension wholesale (empty clears).
    scene_time / timeline: taken when present (including empty string / []).
    plans: taken when key present; omitted key keeps prior plans.
    """
    base = prev if prev and scene_has_content(prev) else empty_scene()
    has_clothing = "clothing" in mouth_fields
    has_positions = "positions" in mouth_fields
    has_time = "scene_time" in mouth_fields
    has_timeline = "timeline" in mouth_fields
    has_plans = "plans" in mouth_fields

    if not (has_clothing or has_positions or has_time or has_timeline or has_plans):
        return sanitize_scene(base)

    next_sc = {
        "clothing": base.get("clothing") or [],
        "positions": base.get("positions") or [],
        "scene_time": base.get("scene_time") or "",
        "timeline": base.get("timeline") or [],
        "plans": base.get("plans") or [],
        "updated_at": time.time(),
    }

    if has_clothing:
        next_sc["clothing"] = mouth_fields.get("clothing") or []
    if has_positions:
        next_sc["positions"] = mouth_fields.get("positions") or []
    if has_time:
        next_sc["scene_time"] = mouth_fields.get("scene_time") or ""
    if has_timeline:
        next_sc["timeline"] = mouth_fields.get("timeline") or []
    if has_plans:
        next_sc["plans"] = mouth_fields.get("plans") or []

    # Soft legacy: empty temporal + had prior → keep prior temporal if mouth
    # only sent clothing/positions without time fields.
    if (
        not next_sc["scene_time"]
        and not next_sc["timeline"]
        and prev
        and (prev.get("scene_time") or prev.get("timeline"))
        and not has_time
        and not has_timeline
    ):
        next_sc["scene_time"] = prev.get("scene_time") or ""
        next_sc["timeline"] = prev.get("timeline") or []
        if not has_plans:
            next_sc["plans"] = prev.get("plans") or []

    return sanitize_scene(next_sc)


def format_scene_block(sc: dict | None, *, for_agent: bool = True) -> str:
    """Render live scene for pillar / mouth injection."""
    if not scene_has_content(sc):
        return ""
    assert sc is not None

    parts: list[str] = []
    if for_agent:
        parts.append(
            "## Live scene state (your last snapshot — re-author every reply via JSON)"
        )
    else:
        parts.append("## Live scene state")

    plans = sc.get("plans") or []
    scene_time = (sc.get("scene_time") or "").strip()
    timeline = sc.get("timeline") or []

    if scene_time or timeline or plans:
        parts.append("### Fiction time (scene_time + timeline + plans)")
        parts.append(f"**Now:** {scene_time or '(none recorded)'}")
        if timeline:
            parts.append("Timeline — past → now (oldest → newest):")
            for e in timeline:
                parts.append(f"- {e['when']}: {e['what']}")
        else:
            parts.append("Timeline: (none recorded)")
        if plans:
            parts.append("Plans — open future relative to Now (soonest first):")
            for e in plans:
                parts.append(f"- {e['when']}: {e['what']}")
        else:
            parts.append("Plans: (none open)")
        if for_agent:
            parts.append(
                "Fiction time is for narrative coherence, not strict clockkeeping. "
                "scene_time is a soft Now (phase/day), not a wall clock — copy it forward "
                "when the beat has not moved; update only when the story needs time to move. "
                "timeline = past beats that still matter; plans = fuzzy open commitments "
                "(dinner in ~2 hours) — rough labels are fine. When you jump (sleep, "
                "fast-forward, tomorrow is now), advance scene_time and drop/rough-update "
                "plans as needed."
            )

    clothing = sc.get("clothing") or []
    if clothing:
        parts.append("### Clothing + presentation (current_clothing_scene_members)")
        for e in clothing:
            parts.append(f"- {e['name']}: {e['clothing']}")
    else:
        parts.append("### Clothing + presentation\n- (none recorded)")

    positions = sc.get("positions") or []
    if positions:
        parts.append("### Positions (current_position_in_scene)")
        for e in positions:
            parts.append(f"- {e['name']}: {e['position']}")
    else:
        parts.append("### Positions\n- (none recorded)")

    if for_agent:
        parts.append(
            "This block is prior state you wrote last turn — not a host lock. "
            "YOU re-author scene fields every reply: copy forward when nothing moved; "
            "update when clothes, place, time, timeline, or plans change. "
            "List everyone present in clothing and positions when the scene has bodies."
        )

    return "\n".join(parts)


def mouth_scene_instructions() -> str:
    """Appended to mouth system prompt — contract for scene JSON fields."""
    return """\
[Live scene contract]
Every reply is structured JSON (host schema). Include scene fields every final reply:
  "scene_time": soft fiction Now (phase/day/place), "" only if pure logistics
  "timeline": [ {"when": short fuzzy label, "what": past beat} ] — past→now, max ~12
  "plans": [ {"when": relative label, "what": open future} ] — max 6, soonest first
  "current_clothing_scene_members": [ {"name": "Mina"|"Ryan"|…, "clothing": concrete prose} ]
  "current_position_in_scene": [ {"name": "…", "position": room/pose/proximity} ]

Rules:
- Full snapshot each turn for clothing/positions (not a delta). Empty [] only for pure tech.
- Copy prior live scene strings when nothing changed; update when this beat moves them.
- Plans = open future only; done/cancelled plans drop off. Past goes on timeline.
- Voice the user reads goes in "content" (or "response_in_mina_voice"). Never put scene bookkeeping in voice.
- Host re-injects your last snapshot next turn as "Live scene state"."""
