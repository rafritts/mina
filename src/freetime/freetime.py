"""
FREETIME loop — Mina's inner life between user messages.

Architecture: same pillar chain as a regular turn, but input is a synthetic
system message and output routes to memory (conversation log) rather than back
to the user. Cadence is circadian-driven via orexin/adenosine from the sim.

Flow:
  1. Cadence gate — skip if orexin low + adenosine high (sleep pressure too high)
  2. Consolidation — hippocampus consolidates pending conversation into RAG/KAG
  3. Pillar chain — encoder → insula → hippocampus → PFC (same as pipeline.run_turn)
  4. Mina LLM call with tools — tool dispatch loop (up to _MAX_TOOL_ROUNDS)
  5. Memory write — final response appended to conversation log for next consolidation
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import (
    MODEL, CONTEXT_MODEL, RELATIONSHIP_DIR, get_conversation_file, RUN_DIR
)
from src.sim.sim import Sim

from .tools import FREETIME_TOOLS, call_tool

_MAX_TOOL_ROUNDS = 5
_LAST_FREETIME_FILE = os.path.join(RUN_DIR, "last_freetime.json")
_FREETIME_LOG_FILE = os.path.join(RUN_DIR, "freetime_log.jsonl")
_MAX_FREETIME_LOG = 200

# Cadence: while awake and not under crushing sleep pressure.
# Auto-sleep in the sim owns recovery; FREETIME must not permanently refuse
# when adenosine is high (that blocked the only autonomous loop).
_OREXIN_FLOOR      = 2   # skip only if deeply hypo-aroused
_ADENOSINE_SKIP    = 9   # skip active FREETIME only near forced sleep
_MIN_INTERVAL_S    = 1800  # never fire more often than every 30 minutes


def _last_freetime_ts() -> float:
    try:
        with open(_LAST_FREETIME_FILE) as f:
            return float(json.load(f).get("ts", 0))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.0


def _save_freetime_record(record: dict) -> None:
    """Write last_freetime.json and append to rolling freetime_log.jsonl."""
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(_LAST_FREETIME_FILE, "w") as f:
        json.dump(record, f, indent=2)
    try:
        with open(_FREETIME_LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
        # Rotate
        with open(_FREETIME_LOG_FILE) as f:
            lines = f.read().splitlines()
        if len(lines) > _MAX_FREETIME_LOG:
            with open(_FREETIME_LOG_FILE, "w") as f:
                f.write("\n".join(lines[-_MAX_FREETIME_LOG:]) + "\n")
    except OSError as e:
        log("FREETIME", f"Log append failed: {e}")


def _tool_label(name: str, args: dict | None = None) -> str:
    """Short chip label — never a multi-sentence dump."""
    args = args or {}
    if name == "record_diary":
        return "Diary"
    if name == "eat":
        return "Eat"
    if name == "drink":
        d = (args.get("description") or "").lower()
        if "water" in d:
            return "Water"
        if any(w in d for w in ("coffee", "espresso", "latte")):
            return "Coffee"
        if "tea" in d:
            return "Tea"
        return "Drink"
    if name == "do_action":
        act = (args.get("activity") or "action").strip()
        if len(act) > 22:
            act = act[:21] + "…"
        return act or "Action"
    if name == "sleep":
        return "Sleep"
    if name == "web_search":
        return "Web"
    if name == "x_search":
        return "X"
    return name.replace("_", " ")


def _tool_preview(name: str, args: dict) -> str:
    """One-line detail for logs/events (not for chips)."""
    if name == "eat":
        desc = (args.get("description") or "something").strip()
        return f"ate {desc[:60]}{'…' if len(desc) > 60 else ''}"
    if name == "drink":
        desc = (args.get("description") or "something").strip()
        return f"drank {desc[:60]}{'…' if len(desc) > 60 else ''}"
    if name == "do_action":
        act = (args.get("activity") or "something").strip()
        return act[:70] + ("…" if len(act) > 70 else "")
    if name == "record_diary":
        entry = (args.get("entry") or "").strip().replace("\n", " ")
        return f"diary: {entry[:60]}{'…' if len(entry) > 60 else ''}"
    if name == "sleep":
        reason = (args.get("reason") or "").strip()
        return f"went to sleep{(' — ' + reason[:40]) if reason else ''}"
    if name in ("web_search", "x_search"):
        q = (args.get("query") or "").strip()
        return f"{name}: {q[:50]}{'…' if len(q) > 50 else ''}"
    return name


def _body_from_tools(tools: list[dict]) -> str:
    """Best narrative when the session has no final reply."""
    # Prefer the last diary entry (richest solitary note).
    for t in reversed(tools):
        if t.get("name") != "record_diary":
            continue
        entry = ((t.get("args") or {}).get("entry") or "").strip()
        if not entry:
            continue
        para = entry.split("\n\n")[0].replace("\n", " ").strip()
        return para[:360] + ("…" if len(para) > 360 else "")
    # Then last physical action / drink / eat.
    for t in reversed(tools):
        name = t.get("name") or ""
        args = t.get("args") or {}
        if name == "do_action":
            act = (args.get("activity") or "").strip()
            desc = (args.get("description") or "").strip()
            line = f"{act}. {desc}".strip(". ").strip()
            if line:
                return line[:240]
        if name == "drink":
            d = (args.get("description") or "something").strip()
            return f"Drank {d}"[:240]
        if name == "eat":
            d = (args.get("description") or "something").strip()
            return f"Ate {d}"[:240]
        if name == "sleep":
            reason = (args.get("reason") or "").strip()
            return f"Went to sleep{(' — ' + reason) if reason else ''}."
    return ""


def _unique_labels(tools: list[dict]) -> list[str]:
    """Dedupe chip labels in order, e.g. 5× diary → one 'Diary'."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tools:
        label = (t.get("label") or _tool_label(t.get("name") or "", t.get("args") or "")).strip()
        if not label or label in seen:
            continue
        seen.add(label)
        out.append(label)
        if len(out) >= 6:
            break
    return out


def _tool_args_for_api(name: str, args: dict, *, full: bool) -> dict:
    """Trim tool args for list view; keep diary/action text for detail."""
    if not args:
        return {}
    if full:
        # Cap runaway strings but keep readable full diary entries.
        out: dict = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 4000:
                out[k] = v[:4000] + "…"
            else:
                out[k] = v
        return out
    # Compact list view — labels only need short hints.
    if name == "record_diary" and args.get("entry"):
        e = str(args["entry"]).replace("\n", " ").strip()
        return {"entry": e[:100] + ("…" if len(e) > 100 else "")}
    if name in ("eat", "drink") and args.get("description"):
        return {"description": str(args["description"])[:80]}
    if name == "do_action":
        return {
            k: str(args[k])[:60]
            for k in ("activity", "description")
            if args.get(k)
        }
    if name == "sleep" and args.get("reason"):
        return {"reason": str(args["reason"])[:80]}
    if name in ("web_search", "x_search") and args.get("query"):
        return {"query": str(args["query"])[:80]}
    return {}


def _session_body(rec: dict, tools: list[dict]) -> str:
    reply = (rec.get("reply") or "").strip()
    if reply:
        return reply
    body = _body_from_tools(tools if tools else (rec.get("tools") or []))
    if body:
        return body
    preview = (rec.get("preview") or rec.get("summary") or rec.get("body") or "").strip()
    if preview and " · " not in preview:
        return preview
    return "Quiet free time — no note."


def _normalize_session(rec: dict, *, full: bool = False) -> dict:
    """
    Shape a session for the UI.

    compact (full=False): short labels, summary body, no pillar context — for lists.
    full=True: full tool args + pillar context — for Lab Free time detail.
    """
    raw_tools = rec.get("tools") or []
    tools: list[dict] = []
    for t in raw_tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name") or "tool"
        args = t.get("args") if isinstance(t.get("args"), dict) else {}
        tools.append({
            "name": name,
            "label": t.get("label") or _tool_label(name, args),
            "preview": (t.get("preview") or _tool_preview(name, args))[:80],
            "result": (t.get("result") or "")[:300] if full else "",
            "args": _tool_args_for_api(name, args, full=full),
        })

    body = _session_body(rec, raw_tools if raw_tools else tools)
    labels = _unique_labels(tools)
    summary = body.replace("\n", " ").strip()
    if len(summary) > 200:
        summary = summary[:199] + "…"

    ts = rec.get("ts")
    out: dict = {
        "ts": ts,
        "ts_human": (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
            if ts
            else None
        ),
        "started_at": rec.get("started_at"),
        "duration_s": rec.get("duration_s"),
        "message": rec.get("message"),
        "reply": (rec.get("reply") or "").strip(),
        "body": body,
        "summary": summary,
        "preview": summary,
        "labels": labels,
        "tools": tools,
        "source": rec.get("source") or "freetime",
        "has_context": bool(rec.get("context")),
    }

    if full:
        ctx = rec.get("context")
        if isinstance(ctx, dict) and ctx:
            out["context"] = ctx
        else:
            # Backfill from last_context if this is the latest freetime turn.
            out["context"] = _context_from_last_context(float(ts or 0))
            out["has_context"] = bool(out["context"])
        # Full diary entries for the Tools section
        out["diaries"] = [
            (t.get("args") or {}).get("entry")
            for t in tools
            if t.get("name") == "record_diary" and (t.get("args") or {}).get("entry")
        ]
    return out


def _context_from_last_context(session_ts: float) -> dict | None:
    """If last_context.json is a matching freetime turn, reuse its pillar dump."""
    try:
        from src.brain.context_log import read_last_context
        last = read_last_context() or {}
    except Exception:
        return None
    if last.get("source") != "freetime":
        return None
    last_ts = float(last.get("ts") or 0)
    if session_ts and last_ts and abs(last_ts - session_ts) > 120:
        return None
    return {
        "encoder": last.get("encoder") or {},
        "relationship_modifier": last.get("relationship_modifier"),
        "sim_snapshot": last.get("sim_snapshot") or {},
        "big5": last.get("big5") or {},
        "assembly": last.get("assembly") or {},
        "insula": last.get("insula") or {},
        "hippocampus": last.get("hippocampus") or {},
        "pfc": last.get("pfc") or {},
        "scene": last.get("scene") or {},
        "system_prompt": last.get("system_prompt") or "",
    }


def _load_raw_sessions(limit: int) -> list[dict]:
    """Load raw (unnormalized) sessions newest-first."""
    limit = max(1, min(int(limit or 30), 100))
    sessions: list[dict] = []

    try:
        with open(_FREETIME_LOG_FILE) as f:
            lines = f.read().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sessions.append(rec)
            if len(sessions) >= limit:
                break
    except FileNotFoundError:
        pass

    if len(sessions) < limit:
        seen_ts = {float(s.get("ts") or 0) for s in sessions}
        for hit in _scan_conversation_freetime(limit * 2):
            ts = float(hit.get("ts") or 0)
            if any(abs(ts - t) < 5 for t in seen_ts):
                continue
            sessions.append(hit)
            seen_ts.add(ts)
            if len(sessions) >= limit:
                break

    sessions.sort(key=lambda s: float(s.get("ts") or 0), reverse=True)
    return sessions[:limit]


def _raw_last_record() -> dict | None:
    try:
        with open(_LAST_FREETIME_FILE) as f:
            last = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not last:
        return None
    if not (last.get("reply") or last.get("preview") or last.get("tools") or last.get("body")):
        return None
    return last


def read_freetime_history(limit: int = 30, detail_ts: float | None = None) -> dict:
    """
    Recent free-time for UI.

    Returns compact list by default. When detail_ts is set, also returns
    `detail` with full tools + pillar context for that session.
    """
    raw = _load_raw_sessions(limit)
    recent = [_normalize_session(s, full=False) for s in raw]

    last_raw = _raw_last_record()
    if last_raw is None and raw:
        last_raw = raw[0]
    last = _normalize_session(last_raw, full=False) if last_raw else None

    detail = None
    if detail_ts is not None:
        target = float(detail_ts)
        match = None
        # Prefer exact/near match in raw log
        for s in raw:
            if abs(float(s.get("ts") or 0) - target) < 1.5:
                match = s
                break
        if match is None and last_raw and abs(float(last_raw.get("ts") or 0) - target) < 1.5:
            match = last_raw
        if match is None:
            # Scan full log for older sessions beyond limit
            match = _find_raw_session(target)
        if match is not None:
            detail = _normalize_session(match, full=True)
        elif recent:
            # Fall back to nearest recent
            nearest = min(recent, key=lambda s: abs(float(s.get("ts") or 0) - target))
            if abs(float(nearest.get("ts") or 0) - target) < 5:
                # Re-load full from raw if possible
                for s in raw:
                    if abs(float(s.get("ts") or 0) - float(nearest["ts"])) < 1.5:
                        detail = _normalize_session(s, full=True)
                        break
                if detail is None:
                    detail = _normalize_session(nearest, full=True)

    return {"last": last, "recent": recent, "detail": detail}


def _find_raw_session(ts: float) -> dict | None:
    try:
        with open(_FREETIME_LOG_FILE) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return None
    best = None
    best_d = 1e18
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = abs(float(rec.get("ts") or 0) - ts)
        if d < best_d:
            best_d = d
            best = rec
    return best if best is not None and best_d < 2.0 else None


def format_freetime_markdown(session: dict) -> str:
    """Human-readable dump of a full free-time session (Lab / agents)."""
    lines: list[str] = []
    lines.append("# Mina free time")
    lines.append("")
    lines.append(f"- **when:** {session.get('ts_human') or session.get('ts') or '—'}")
    if session.get("duration_s") is not None:
        lines.append(f"- **duration:** {session['duration_s']}s")
    labels = session.get("labels") or []
    if labels:
        lines.append(f"- **actions:** {', '.join(labels)}")
    lines.append("")

    lines.append("## Synthetic input")
    lines.append("")
    lines.append((session.get("message") or "(none)").strip() or "(none)")
    lines.append("")

    lines.append("## Tools")
    lines.append("")
    tools = session.get("tools") or []
    if not tools:
        lines.append("_(none)_")
    for i, t in enumerate(tools, 1):
        label = t.get("label") or t.get("name") or "tool"
        lines.append(f"### {i}. {label} (`{t.get('name')}`)")
        lines.append("")
        args = t.get("args") or {}
        if t.get("name") == "record_diary" and args.get("entry"):
            lines.append(args["entry"].strip())
        elif args:
            for k, v in args.items():
                lines.append(f"- **{k}:** {v}")
        if t.get("result"):
            lines.append("")
            lines.append(f"_result:_ {t['result']}")
        lines.append("")

    lines.append("## Reply")
    lines.append("")
    lines.append((session.get("reply") or session.get("body") or "(none)").strip() or "(none)")
    lines.append("")

    ctx = session.get("context") or {}
    if ctx:
        a = ctx.get("assembly") or {}
        lines.append("## Encoder")
        lines.append("")
        lines.append(json.dumps(ctx.get("encoder") or {}, indent=2))
        lines.append("")
        lines.append("## Decoder (chemistry)")
        lines.append("")
        lines.append(json.dumps(ctx.get("sim_snapshot") or {}, indent=2)[:4000])
        lines.append("")
        lines.append("## Insula")
        lines.append("")
        lines.append(json.dumps(ctx.get("insula") or {}, indent=2))
        lines.append("")
        lines.append("## Hippocampus")
        lines.append("")
        lines.append(json.dumps(ctx.get("hippocampus") or {}, indent=2))
        lines.append("")
        lines.append("## PFC")
        lines.append("")
        lines.append(json.dumps(ctx.get("pfc") or {}, indent=2))
        lines.append("")
        lines.append("## Context assembly")
        lines.append("")
        lines.append("### Window")
        lines.append("")
        lines.append((a.get("window_context") or "(none)").strip() or "(none)")
        lines.append("")
        lines.append("### RAG")
        lines.append("")
        lines.append((a.get("rag_context") or "(none)").strip() or "(none)")
        lines.append("")
        lines.append("### KAG")
        lines.append("")
        lines.append((a.get("kag_context") or "(none)").strip() or "(none)")
        lines.append("")
        lines.append("## System prompt")
        lines.append("")
        lines.append((ctx.get("system_prompt") or "(none)").strip() or "(none)")
        lines.append("")

    return "\n".join(lines)


def write_last_freetime_markdown(session: dict) -> None:
    path = os.path.join(RUN_DIR, "last_freetime.md")
    try:
        with open(path, "w") as f:
            f.write(format_freetime_markdown(session))
    except OSError as e:
        log("FREETIME", f"last_freetime.md write failed: {e}")


def _scan_conversation_freetime(limit: int) -> list[dict]:
    """Pull freetime assistant replies from conversation-*.jsonl (newest first)."""
    import glob

    pattern = os.path.join(RUN_DIR, "conversation-*.jsonl")
    files = sorted(glob.glob(pattern), reverse=True)[:14]  # ~2 weeks
    hits: list[dict] = []
    for path in files:
        try:
            with open(path) as f:
                lines = f.readlines()
        except OSError:
            continue
        # Walk newest-first within file
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("source") != "freetime":
                continue
            if obj.get("role") != "assistant":
                continue
            content = (obj.get("content") or "").strip()
            if not content:
                continue
            hits.append({
                "ts": float(obj.get("ts") or 0),
                "reply": content,
                "preview": content[:160].replace("\n", " "),
                "tools": [],
                "source": "conversation",
            })
            if len(hits) >= limit:
                return hits
    return hits


def should_fire(sim: Sim) -> bool:
    """Return True if FREETIME should fire now based on chemistry and cooldown."""
    if time.time() - _last_freetime_ts() < _MIN_INTERVAL_S:
        return False
    # Sim auto-sleep handles recovery; no active free-time while asleep.
    if sim.is_sleeping():
        log("FREETIME", "Sleeping — skipping active free-time.")
        return False
    snapshot = sim.snapshot()
    orexin   = snapshot.get("orexin",   {}).get("normalized", 5)
    adenosine = snapshot.get("adenosine", {}).get("normalized", 5)
    if orexin < _OREXIN_FLOOR:
        log("FREETIME", f"Orexin too low ({orexin}) — skipping.")
        return False
    if adenosine >= _ADENOSINE_SKIP:
        log("FREETIME", f"Adenosine near sleep threshold ({adenosine}) — skipping (sim will sleep).")
        return False
    return True


def _build_synthetic_message(sim: Sim) -> str:
    """Build the synthetic input that replaces the user message in FREETIME."""
    now_str   = time.strftime("%-I:%M %p", time.localtime())
    day_str   = time.strftime("%A", time.localtime())
    last_ts   = _last_freetime_ts()
    idle_s    = time.time() - last_ts if last_ts > 0 else 0

    parts = [f"It is {day_str}, {now_str}. Nobody is here."]

    if idle_s > 3600:
        hours = idle_s / 3600
        parts.append(f"You have been alone for {hours:.1f} hours.")
    elif idle_s > 60:
        mins = int(idle_s / 60)
        parts.append(f"You have been alone for {mins} minutes.")

    parts.append("This is your free time.")
    return " ".join(parts)


def _append_to_conversation(role: str, content: str, source: str = "freetime") -> None:
    path = get_conversation_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"role": role, "content": content, "ts": time.time(), "source": source}) + "\n")


async def run_freetime(sim: Sim) -> None:
    """Run one FREETIME session. Called by the main loop when cadence allows."""
    log("FREETIME", "Starting.")
    started_at = time.time()
    tools_used: list[dict] = []

    # ── 1. Consolidation ──────────────────────────────────────────────────────
    from src.hippocampus.hippocampus import (
        build_kag_context, consolidate, consolidate_relationship,
        sliding_rag_write
    )

    kag_context = await asyncio.to_thread(build_kag_context)

    # Relationship consolidation — one per tracked person
    if os.path.exists(RELATIONSHIP_DIR):
        for fname in os.listdir(RELATIONSHIP_DIR):
            if not fname.endswith(".md"):
                continue
            person = fname[:-3]
            try:
                await asyncio.to_thread(consolidate_relationship, person)
            except Exception as e:
                log("FREETIME/REL", f"Error consolidating {person}: {e}")

    try:
        reflection = await asyncio.to_thread(consolidate, kag_context)
        log("FREETIME", f"Consolidation: {reflection.get('reflection_summary', '')[:80]}")
    except Exception as e:
        log("FREETIME/CONSOLIDATE", f"Error: {e}")

    # ── 2. Build synthetic message ─────────────────────────────────────────────
    synthetic_message = _build_synthetic_message(sim)
    log("FREETIME", f"Input: {synthetic_message}")

    # ── 3. Pillar chain ───────────────────────────────────────────────────────
    from src.brain.encoder import encode
    from src.brain.insula import run_insula
    from src.brain.hippocampus_pillar import run_hippocampus
    from src.brain.pfc import run_pfc, build_system_prompt, _load_identity, _load_customization
    from src.brain.context_assembly import assemble_window_context, assemble_rag_context
    from src.hippocampus.hippocampus import (
        build_rag_context_dual, sliding_rag_query
    )
    from src.brain.pipeline import (
        _load_decoder_window, _load_prior_emotional_state
    )
    from src.brain.stage_direction import visible_speech

    decoder_window = _load_decoder_window()

    encoder_output = await asyncio.to_thread(encode, synthetic_message, decoder_window[-10:])
    await asyncio.to_thread(sim.apply_chemistry_from_encoder, encoder_output, 1.0)

    decoded = await asyncio.to_thread(sim.snapshot)
    big5    = sim.get_big5()
    prior   = _load_prior_emotional_state()
    insula_output = await asyncio.to_thread(run_insula, decoded, big5, prior)

    kag_ctx, sliding_res, (semi_recent, historical) = await asyncio.gather(
        asyncio.to_thread(build_kag_context, synthetic_message),
        asyncio.to_thread(sliding_rag_query, synthetic_message),
        asyncio.to_thread(build_rag_context_dual, synthetic_message),
    )
    experiences = "\n".join(filter(None, [semi_recent, historical]))

    window_ctx, rag_ctx = await asyncio.gather(
        asyncio.to_thread(assemble_window_context, decoder_window),
        asyncio.to_thread(assemble_rag_context, sliding_res, experiences),
    )

    context_output = await asyncio.to_thread(run_hippocampus, insula_output, window_ctx, rag_ctx)
    pfc_output     = await asyncio.to_thread(run_pfc, insula_output, context_output, synthetic_message, big5)

    from src.brain.time_context import format_host_time_block

    system_prompt = build_system_prompt(insula_output, context_output, pfc_output)
    if kag_ctx:
        system_prompt += f"\n\n[Memory]\n{kag_ctx}"
    # Synthetic message already states day/time; system block keeps mouth aligned
    # with the same wall clock the sim circadian uses.
    system_prompt += "\n\n" + format_host_time_block(
        last_activity_ts=_last_freetime_ts() or None,
    )
    system_prompt += "\n\n[FREETIME] No user is present. Use tools to act, record, or explore. Record a diary entry when you have something genuine to write."

    # ── 4. Mina LLM call with tool dispatch loop ──────────────────────────────
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    # Include recent window context
    for m in decoder_window[-6:]:
        if m.get("role") not in ("user", "assistant") or not m.get("content"):
            continue
        content = m["content"]
        if m["role"] == "user":
            content = visible_speech(content)
            if not content:
                continue
        messages.append({"role": m["role"], "content": content})
    messages.append({"role": "user", "content": synthetic_message})

    _append_to_conversation("user", synthetic_message)

    final_reply = ""
    for round_num in range(_MAX_TOOL_ROUNDS):
        resp = await asyncio.to_thread(
            chat_create,
            model=MODEL,
            messages=messages,
            max_tokens=1024,
            tools=FREETIME_TOOLS,
            tool_choice="auto",
        )
        choice = resp.choices[0]
        msg    = choice.message

        # Parse tool calls from response
        tool_calls = getattr(msg, "tool_calls", None) or []
        content    = msg.content or ""

        if not tool_calls:
            final_reply = content
            break

        # Execute tool calls
        messages.append({"role": "assistant", "content": content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]})

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, ValueError):
                args = {}
            log("FREETIME", f"Tool call {round_num+1}: {name}({list(args.keys())})")
            result = await asyncio.to_thread(call_tool, name, args, sim)
            tool_entry = {
                "name": name,
                "args": args,
                "preview": _tool_preview(name, args),
                "result": (result or "")[:200],
            }
            tools_used.append(tool_entry)
            try:
                from src.application.infra.events import emit as emit_event
                emit_event(
                    "tool",
                    tool_entry["preview"],
                    {"tool": name, "args": args, "result": result[:200], "source": "freetime"},
                )
            except Exception:
                pass
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # ── 5. Memory write ───────────────────────────────────────────────────────
    if final_reply:
        log("FREETIME", f"Response: {final_reply[:100]}")
        _append_to_conversation("assistant", final_reply)
        # Write to sliding RAG so future retrieval captures this moment
        window_with_freetime = decoder_window + [
            {"role": "user", "content": synthetic_message},
            {"role": "assistant", "content": final_reply},
        ]
        await asyncio.to_thread(sliding_rag_write, window_with_freetime)

    # ── 6. Context assembly dump (same as chat turns) ─────────────────────────
    finished_at = time.time()
    try:
        from src.brain.pipeline import _persist_context
        _persist_context(
            ts=finished_at,
            username="freetime",
            message=synthetic_message,
            encoder_output=encoder_output,
            relationship_modifier=1.0,
            decoder_snapshot=decoded,
            big5=big5,
            window_context=window_ctx,
            rag_context=rag_ctx,
            kag_context=kag_ctx or "",
            sliding_result=sliding_res or "",
            experiences_result=experiences or "",
            insula_output=insula_output,
            context_output=context_output,
            pfc_output=pfc_output,
            system_prompt=system_prompt,
            reply=final_reply or "",
            skipped=False,
            source="freetime",
        )
    except Exception as e:
        log("FREETIME/CONTEXT", str(e))

    # ── 7. Persist for UI (what she did alone + pillars) ──────────────────────
    tool_rows = [
        {
            "name": t["name"],
            "label": _tool_label(t["name"], t.get("args") or {}),
            "preview": t["preview"],
            "args": t["args"],
            "result": t.get("result") or "",
        }
        for t in tools_used
    ]
    pillar_context = {
        "encoder": encoder_output or {},
        "relationship_modifier": 1.0,
        "sim_snapshot": decoded or {},
        "big5": big5 or {},
        "assembly": {
            "window_context": window_ctx or "",
            "rag_context": rag_ctx or "",
            "kag_context": kag_ctx or "",
            "sliding_raw": sliding_res or "",
            "experiences_raw": experiences or "",
        },
        "insula": insula_output or {},
        "hippocampus": context_output or {},
        "pfc": pfc_output or {},
        "system_prompt": system_prompt or "",
    }
    # Disk record keeps full tools + pillars; API list view normalizes compact.
    raw_record = {
        "ts": finished_at,
        "started_at": started_at,
        "duration_s": round(finished_at - started_at, 1),
        "message": synthetic_message,
        "reply": final_reply or "",
        "tools": tool_rows,
        "context": pillar_context,
        "source": "freetime",
    }
    # Precompute body/summary/labels for last_freetime.json convenience.
    display = _normalize_session(raw_record, full=True)
    to_store = {
        **raw_record,
        "body": display.get("body"),
        "summary": display.get("summary"),
        "preview": display.get("summary"),
        "labels": display.get("labels"),
    }
    _save_freetime_record(to_store)
    write_last_freetime_markdown(display)
    try:
        from src.application.infra.events import emit as emit_event
        labels = display.get("labels") or []
        event_preview = display.get("summary") or display.get("body") or "free time"
        if labels:
            event_preview = f"{', '.join(labels)} — {event_preview}"
        emit_event("activity", event_preview[:200], {
            "source": "freetime",
            "tools": [t["name"] for t in tool_rows],
            "labels": labels,
            "reply": (final_reply or "")[:400],
        })
    except Exception:
        pass

    log("FREETIME", "Complete.")
