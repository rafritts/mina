"""
Pipeline — per-turn orchestration.

For each incoming message:
  1. Encoder (amygdala) — state-blind perception
  2. Chemistry function — encoder → Class 1 deltas
  3. Decoder snapshot — ChemicalState → pillar-legible JSON
  4. Insula pillar — decoded chemistry → felt state
  5. Memory retrieval — parallel: KAG + RAG (sliding + episodic)
  6. Context assembly — synthesize raw memory into summaries
  7. Hippocampus pillar — felt state + context → situational summary
  8. PFC pillar — everything → response strategy + system prompt
  9. Mina LLM call — system prompt + conversation window → reply

Conversation window and JSONL log are managed here.
Sliding RAG write is called after each message (user and Mina).
Optional send_photo tool (comfy-fe) when image_count allows.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.application.infra.stream_bus import stream_bus
from src.config.config import MODEL, get_conversation_file, RUN_DIR
from src.sim.sim import Sim
from src.sim.decoder import format_decoder_output

from .encoder import encode
from .insula import run_insula, format_emotional_state_block
from .hippocampus_pillar import run_hippocampus
from .pfc import run_pfc, build_system_prompt
from .context_assembly import assemble_window_context, assemble_rag_context
from .context_log import build_record, write_last_context
from .scene_context import (
    apply_scene_from_mouth,
    clear_scene,
    format_scene_block,
    load_scene,
    mouth_scene_instructions,
    save_scene,
    scene_fields_from_mouth,
    scene_has_content,
)
from .chat_tools import (
    CHAT_TOOLS,
    call_chat_tool,
    max_photos,
    parse_tool_args,
    photo_turn_context,
)
from .time_context import format_host_time_block


def _emit_stage(stage: str, label: str) -> None:
    stream_bus.emit("stage", {"stage": stage, "label": label})


def _memory_excerpts(text: str, bucket: str, limit: int = 3) -> None:
    """Emit short rag_hit events from assembled memory blobs."""
    if not text or not text.strip():
        return
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    for i, chunk in enumerate(chunks[:limit]):
        excerpt = chunk[:220] + ("…" if len(chunk) > 220 else "")
        stream_bus.emit("rag_hit", {"index": i, "excerpt": excerpt, "bucket": bucket})

_DECODER_WINDOW_MAX = 20  # rolling window of raw messages for context assembly
_MINA_WINDOW        = 8   # messages Mina receives directly
_MAX_TOOL_ROUNDS    = 6


def _load_decoder_window() -> list[dict]:
    path = os.path.join(RUN_DIR, "decoder_window.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_decoder_window(window: list[dict]) -> None:
    path = os.path.join(RUN_DIR, "decoder_window.json")
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(window, f)


def _append_conversation(role: str, content) -> None:
    path = get_conversation_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"role": role, "content": content, "ts": time.time()}) + "\n")


def rewind_for_redo(user_message: str) -> dict:
    """
    Drop the trailing turn so redo can re-run without duplicating the user message.

    Pops a trailing assistant (if present), then a trailing user whose content
    matches user_message, from decoder_window and today's conversation log.
    Safe no-op when nothing matches (e.g. failed mouth before window save).
    """
    target = (user_message or "").strip()
    popped_window: list[str] = []
    window = _load_decoder_window()
    if window and window[-1].get("role") == "assistant":
        window.pop()
        popped_window.append("assistant")
    if (
        window
        and window[-1].get("role") == "user"
        and (window[-1].get("content") or "").strip() == target
    ):
        window.pop()
        popped_window.append("user")
    if popped_window:
        _save_decoder_window(window)

    popped_log: list[str] = []
    path = get_conversation_file()
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    rows: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if rows and rows[-1].get("role") == "assistant":
        rows.pop()
        popped_log.append("assistant")
    if (
        rows
        and rows[-1].get("role") == "user"
        and (rows[-1].get("content") or "").strip() == target
    ):
        rows.pop()
        popped_log.append("user")
    if popped_log:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    result = {"window": popped_window, "conversation": popped_log}
    if popped_window or popped_log:
        log("PIPELINE", f"redo rewind: window={popped_window} conversation={popped_log}")
    return result


def _load_prior_emotional_state() -> dict | None:
    path = os.path.join(RUN_DIR, "prior_emotional_state.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_prior_emotional_state(state: dict) -> None:
    path = os.path.join(RUN_DIR, "prior_emotional_state.json")
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


async def run_turn(
    message: str,
    username: str,
    sim: Sim,
    *,
    image_count: str | int = "auto",
    image_aspect: str = "square",
) -> dict:
    """
    Run the full per-turn pipeline.

    Returns {"reply": str, "images": list[str]} where images are host paths
    like /images/<id>.png for the UI (also embedded as markdown in reply).

    image_count: "auto" | 0 | 1..5 — UI pic preference (hard cap on send_photo).
    image_aspect: landscape | square | portrait — forced on host generate.
    """
    ts = time.time()
    log("USER", f"{username}: {message[:120]}")
    photo_cap = max_photos(image_count)
    aspect = image_aspect if image_aspect in ("landscape", "square", "portrait") else "square"

    stream_bus.new_trace()
    stream_bus.emit("stimulus_land", {"preview": message[:280]})
    _emit_stage("sense", "Sensing")

    # Load rolling window
    decoder_window = _load_decoder_window()

    # Append user message to window and conversation log
    decoder_window.append({"role": "user", "content": message, "ts": ts})
    _append_conversation("user", message)

    # ── 1. Encoder (state-blind) ────────────────────────────────────────────
    encoder_output = await asyncio.to_thread(encode, message, decoder_window[:-1])
    axes = {
        k: v for k, v in encoder_output.items() if not isinstance(v, (dict, list))
    }

    # ── 2. Relationship modifier + chemistry function ────────────────────────
    from src.hippocampus.hippocampus import get_relationship_modifier
    relationship_modifier = await asyncio.to_thread(get_relationship_modifier, username)
    log("PIPELINE", f"relationship_modifier({username})={relationship_modifier}")

    chem_deltas = await asyncio.to_thread(
        sim.apply_chemistry_from_encoder, encoder_output, relationship_modifier
    )
    _emit_stage("chemistry", "Chemistry settling")
    # Appraisal + applied Class-1 deltas for mind stream (after chemistry runs)
    stream_bus.emit("encoder", {
        "preview": message[:120],
        "axes": axes,
        "deltas": chem_deltas or {},
        "relationship_modifier": relationship_modifier,
    })

    # ── 3. Sliding RAG write (post-user-message) ─────────────────────────────
    asyncio.create_task(_sliding_rag_write_async(decoder_window))

    # ── 4. Decoder snapshot ─────────────────────────────────────────────────
    decoded = await asyncio.to_thread(sim.snapshot)
    big5    = sim.get_big5()

    # ── 5. Insula pillar ────────────────────────────────────────────────────
    _emit_stage("feel", "Feeling")
    prior_emotional = _load_prior_emotional_state()
    insula_output = await asyncio.to_thread(
        run_insula, decoded, big5, prior_emotional
    )
    stream_bus.emit("emotion_pillar", {
        "dominant_affect": insula_output.get("dominant_affect", ""),
        "trend": insula_output.get("trend", ""),
        "arousal": insula_output.get("arousal", 50),
        "valence": insula_output.get("valence", 50),
        "availability": insula_output.get("availability", ""),
        "dominant_drive": insula_output.get("dominant_drive", ""),
        "emotional_response_texturing": insula_output.get("emotional_response_texturing", ""),
        "emotional_summary": insula_output.get("emotional_summary", ""),
        "somatic": insula_output.get("somatic", ""),
    })

    # ── 6. Memory retrieval (parallel) ──────────────────────────────────────
    _emit_stage("remember", "Remembering")
    from src.hippocampus.hippocampus import (
        build_kag_context, sliding_rag_query, build_rag_context_dual
    )

    kag_context, sliding_result, (semi_recent, historical) = await asyncio.gather(
        asyncio.to_thread(build_kag_context, message),
        asyncio.to_thread(sliding_rag_query, message),
        asyncio.to_thread(build_rag_context_dual, message),
    )
    experiences_result = "\n".join(filter(None, [semi_recent, historical]))
    _memory_excerpts(sliding_result or "", "sliding")
    _memory_excerpts(experiences_result or "", "episodic")
    if kag_context:
        for i, line in enumerate((kag_context or "").split("\n")[:3]):
            line = line.strip()
            if line:
                stream_bus.emit("kag_selection", {
                    "filename": line[:80],
                    "excerpt": line[:200],
                })

    # ── 7. Context assembly + prior live scene ───────────────────────────────
    # Scene is agent-authored last turn; pillars consume it, mouth re-authors.
    prior_scene = load_scene()
    scene_block = format_scene_block(prior_scene, for_agent=True) if scene_has_content(prior_scene) else ""

    window_context, rag_context = await asyncio.gather(
        asyncio.to_thread(assemble_window_context, decoder_window),
        asyncio.to_thread(assemble_rag_context, sliding_result, experiences_result),
    )

    # ── 8. Hippocampus pillar ────────────────────────────────────────────────
    _emit_stage("situate", "Situating")
    context_output = await asyncio.to_thread(
        run_hippocampus, insula_output, window_context, rag_context, scene_block
    )
    stream_bus.emit("context_pillar", {
        "social_context": context_output.get("social_context", ""),
        "urgency": context_output.get("urgency", "none"),
        "notable": context_output.get("notable"),
        "situational_summary": context_output.get("situational_summary", ""),
    })

    # ── 9. PFC pillar ────────────────────────────────────────────────────────
    _emit_stage("decide", "Deciding")
    pfc_output = await asyncio.to_thread(
        run_pfc, insula_output, context_output, message, big5, scene_block
    )
    stream_bus.emit("reasoning", {
        "approach": pfc_output.get("approach", ""),
        "tone": pfc_output.get("tone", ""),
        "internal_reaction": pfc_output.get("internal_reaction", ""),
        "lead_with": pfc_output.get("lead_with", ""),
        "strategy_rationale": pfc_output.get("strategy_rationale", ""),
    })

    if pfc_output.get("skip_primary_response"):
        log("PIPELINE", "PFC chose silence.")
        stream_bus.emit("response_complete", {
            "text": "",
            "token_count": 0,
            "skipped": True,
        })
        _save_prior_emotional_state(insula_output)
        _trim_and_save_window(decoder_window)
        _persist_context(
            ts=ts,
            username=username,
            message=message,
            encoder_output=encoder_output,
            relationship_modifier=relationship_modifier,
            decoder_snapshot=decoded,
            big5=big5,
            window_context=window_context,
            rag_context=rag_context,
            kag_context=kag_context or "",
            sliding_result=sliding_result or "",
            experiences_result=experiences_result or "",
            insula_output=insula_output,
            context_output=context_output,
            pfc_output=pfc_output,
            system_prompt="",
            reply="",
            skipped=True,
            scene=prior_scene if scene_has_content(prior_scene) else None,
        )
        return {"reply": "", "images": []}

    # ── 10. Build system prompt ─────────────────────────────────────────────
    system_prompt = build_system_prompt(
        insula_output, context_output, pfc_output, scene_block=scene_block
    )

    # Append KAG context to system prompt
    if kag_context:
        system_prompt += f"\n\n[Memory]\n{kag_context}"

    # Host wall clock (Kaiya-style) — circadian body time for mouth.
    # Prefer last prior activity ts so idle after this message still reflects gap.
    last_activity_ts = None
    for m in reversed(decoder_window[:-1]):
        t = m.get("ts")
        if isinstance(t, (int, float)) and t > 0:
            last_activity_ts = float(t)
            break
    system_prompt += "\n\n" + format_host_time_block(last_activity_ts=last_activity_ts)
    system_prompt += "\n\n" + photo_turn_context(image_count, aspect)
    system_prompt += "\n\n" + mouth_scene_instructions()

    # ── 11. Mina LLM call (+ optional send_photo tool loop) ────────────────
    _emit_stage("speak", "Speaking")
    mina_window = decoder_window[-_MINA_WINDOW:]
    messages: list[dict] = [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": m["content"]}
        for m in mina_window
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    tools = CHAT_TOOLS if photo_cap > 0 else None
    photo_units: list[str] = []
    photos_sent = 0
    reply = ""
    final_mouth: dict | None = None
    mouth_obj: dict | None = None

    for round_num in range(_MAX_TOOL_ROUNDS):
        create_kwargs: dict = dict(
            model=MODEL,
            messages=messages,
            max_tokens=1024,
            reasoning_effort="none",
            mouth=True,  # voice + scene JSON every mouth call
        )
        if tools and photos_sent < photo_cap:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        resp = await asyncio.to_thread(chat_create, **create_kwargs)
        msg = resp.choices[0].message
        content = msg.content or ""
        tool_calls = getattr(msg, "tool_calls", None) or []
        mouth_obj = getattr(msg, "mouth", None)

        if not tool_calls:
            reply = content
            if isinstance(mouth_obj, dict):
                final_mouth = mouth_obj
            break

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            name = tc.function.name
            args = parse_tool_args(tc.function.arguments)
            if name == "send_photo" and photos_sent >= photo_cap:
                result = f"[send_photo skipped: already sent {photo_cap} this turn]"
            else:
                log("PIPELINE", f"Tool {round_num+1}: {name}")
                result = await asyncio.to_thread(
                    call_chat_tool, name, args, image_aspect=aspect
                )
                if name == "send_photo" and "/images/" in result:
                    photos_sent += 1
                    photo_units.append(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    else:
        # Exhausted tool rounds without a pure text finish
        reply = content if content else ""
        if isinstance(mouth_obj, dict):
            final_mouth = mouth_obj

    # Host photos are authoritative — strip fakes, then ensure every real URL is in reply
    image_urls = _photo_urls(photo_units)
    if photo_units or image_urls:
        reply = _strip_fake_images(reply or "")
        reply = _ensure_photos_in_reply(reply, photo_units, image_urls)
        # Re-extract in case units carried multiple; keep order stable
        image_urls = _photo_urls(photo_units) or _photo_urls([reply])

    # ── 11b. Persist agent-authored live scene ──────────────────────────────
    next_scene = prior_scene
    if isinstance(final_mouth, dict):
        fields = scene_fields_from_mouth(final_mouth)
        if fields:
            applied = apply_scene_from_mouth(prior_scene, fields)
            if applied is not None:
                save_scene(applied)
                next_scene = applied
                log(
                    "SCENE",
                    f"time={applied.get('scene_time', '')[:60]!r} "
                    f"clothing={len(applied.get('clothing') or [])} "
                    f"timeline={len(applied.get('timeline') or [])} "
                    f"plans={len(applied.get('plans') or [])}",
                )
            else:
                clear_scene()
                next_scene = {}
        stream_bus.emit("scene_update", {
            "scene_time": (next_scene or {}).get("scene_time", ""),
            "clothing": (next_scene or {}).get("clothing") or [],
            "positions": (next_scene or {}).get("positions") or [],
            "timeline": (next_scene or {}).get("timeline") or [],
            "plans": (next_scene or {}).get("plans") or [],
        })

    log("MINA", (reply[:120] if reply else "(empty)"))
    if image_urls:
        log("MINA", f"images={image_urls}")

    stream_bus.emit("response_complete", {
        "text": reply or "",
        "token_count": 0,
        "skipped": False,
        "images": image_urls,
    })

    # ── 12. Post-turn bookkeeping ───────────────────────────────────────────
    decoder_window.append({"role": "assistant", "content": reply, "ts": time.time()})
    _append_conversation("assistant", reply)
    asyncio.create_task(_sliding_rag_write_async(decoder_window))

    _save_prior_emotional_state(insula_output)
    _trim_and_save_window(decoder_window)

    # ── 13. Full turn log + last_context.{json,md} ──────────────────────────
    _persist_context(
        ts=ts,
        username=username,
        message=message,
        encoder_output=encoder_output,
        relationship_modifier=relationship_modifier,
        decoder_snapshot=decoded,
        big5=big5,
        window_context=window_context,
        rag_context=rag_context,
        kag_context=kag_context or "",
        sliding_result=sliding_result or "",
        experiences_result=experiences_result or "",
        insula_output=insula_output,
        context_output=context_output,
        pfc_output=pfc_output,
        system_prompt=system_prompt,
        reply=reply,
        skipped=False,
        scene=next_scene if scene_has_content(next_scene) else None,
    )

    return {"reply": reply, "images": image_urls}


def _photo_urls(units: list[str]) -> list[str]:
    """Extract ordered unique /images/... URLs from photo tool results or reply text."""
    import re
    seen: set[str] = set()
    out: list[str] = []
    for text in units:
        if not text:
            continue
        for m in re.finditer(r"\((/images/[^)\s]+)\)", text):
            url = m.group(1)
            if url not in seen:
                seen.add(url)
                out.append(url)
        # bare path fallback
        for m in re.finditer(r"(?<![(\w])/images/[A-Za-z0-9._-]+\.(?:png|jpe?g|webp|gif)", text):
            url = m.group(0)
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out


def _ensure_photos_in_reply(reply: str, photo_units: list[str], image_urls: list[str]) -> str:
    """
    Guarantee host photos appear as markdown in the reply the UI stores.

    Prefer full photo_units (caption + markdown) when the URL is missing from reply;
    otherwise inject a bare ![photo](url) for any missing URL.
    """
    text = (reply or "").rstrip()
    missing_urls = [u for u in image_urls if u not in text]

    if not missing_urls:
        return text

    # Append whole tool units that carry a missing URL (preserves caption)
    for unit in photo_units:
        if any(u in unit for u in missing_urls) and unit not in text:
            text = f"{text}\n\n{unit}".strip() if text else unit
            missing_urls = [u for u in image_urls if u not in text]
            if not missing_urls:
                return text

    for url in missing_urls:
        if url not in text:
            text = f"{text}\n\n![photo]({url})".strip() if text else f"![photo]({url})"
    return text


def _strip_fake_images(text: str) -> str:
    """Remove model-invented image markdown that is not host /images/ or /api/generate/."""
    import re
    def keep(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith("/images/") or url.startswith("/api/generate/"):
            return m.group(0)
        return ""
    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", keep, text).strip()


def _persist_context(
    *,
    ts: float,
    username: str,
    message: str,
    encoder_output: dict,
    relationship_modifier: float,
    decoder_snapshot: dict,
    big5: dict,
    window_context: str,
    rag_context: str,
    kag_context: str,
    sliding_result: str,
    experiences_result: str,
    insula_output: dict,
    context_output: dict,
    pfc_output: dict,
    system_prompt: str,
    reply: str,
    skipped: bool,
    source: str = "chat",
    scene: dict | None = None,
) -> None:
    """Write turns.jsonl append + run/last_context.{json,md}."""
    record = build_record(
        ts=ts,
        username=username,
        message=message,
        source=source,
        encoder_output=encoder_output,
        relationship_modifier=relationship_modifier,
        decoder_snapshot=decoder_snapshot,
        big5=big5,
        window_context=window_context,
        rag_context=rag_context,
        kag_context=kag_context,
        sliding_result=sliding_result,
        experiences_result=experiences_result,
        insula_output=insula_output,
        context_output=context_output,
        pfc_output=pfc_output,
        system_prompt=system_prompt,
        reply=reply,
        skipped=skipped,
        scene=scene,
    )
    write_last_context(record)

    path = os.path.join(RUN_DIR, "turns.jsonl")
    os.makedirs(RUN_DIR, exist_ok=True)
    # Flat turn log keeps pillars + assembly nested for tooling
    turn_row = {
        "ts": ts,
        "ts_human": record["ts_human"],
        "username": username,
        "source": source,
        "message": message,
        "encoder": encoder_output,
        "relationship_modifier": relationship_modifier,
        "sim_snapshot": decoder_snapshot,
        "big5": big5,
        "assembly": record["assembly"],
        "insula": insula_output,
        "hippocampus": context_output,
        "pfc": pfc_output,
        "system_prompt": system_prompt,
        "reply": reply,
        "skipped": skipped,
        "scene": scene or {},
    }
    try:
        with open(path, "a") as f:
            f.write(json.dumps(turn_row) + "\n")
    except OSError as e:
        log("PIPELINE/LOG/ERR", str(e))


def _trim_and_save_window(window: list[dict]) -> None:
    if len(window) > _DECODER_WINDOW_MAX:
        window[:] = window[-_DECODER_WINDOW_MAX:]
    _save_decoder_window(window)


def erase_chat_history() -> dict:
    """
    Wipe conversation-facing history so the next turn starts fresh.

    Clears: conversation logs, decoder window, turn/context dumps, prior
    emotional state from chat, live scene, and sliding (short-term) RAG.

    Keeps: chemistry, episodic RAG, KAG, relationship files.
    """
    from pathlib import Path
    from src.hippocampus.hippocampus import sliding_rag_wipe

    removed: list[str] = []
    run = Path(RUN_DIR)
    targets = [
        run / "decoder_window.json",
        run / "prior_emotional_state.json",
        run / "scene_context.json",
        run / "turns.jsonl",
        run / "last_context.json",
        run / "last_context.md",
        run / "sliding_seq.json",
    ]
    for path in targets:
        try:
            if path.exists():
                path.unlink()
                removed.append(path.name)
        except OSError as e:
            log("PIPELINE/ERASE", f"{path.name}: {e}")

    for path in run.glob("conversation-*.jsonl"):
        try:
            path.unlink()
            removed.append(path.name)
        except OSError as e:
            log("PIPELINE/ERASE", f"{path.name}: {e}")

    try:
        sliding_rag_wipe()
        removed.append("sliding_rag")
    except Exception as e:
        log("PIPELINE/ERASE", f"sliding_rag: {e}")

    log("PIPELINE", f"Chat history erased: {', '.join(removed) or '(nothing)'}")
    return {"ok": True, "removed": removed}


async def _sliding_rag_write_async(window: list[dict]) -> None:
    try:
        from src.hippocampus.hippocampus import sliding_rag_write
        await asyncio.to_thread(sliding_rag_write, window)
    except Exception as e:
        log("PIPELINE/RAG/ERR", str(e))
