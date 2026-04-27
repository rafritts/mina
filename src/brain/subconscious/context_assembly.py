"""
Context assembly — window synthesis and RAG/KAG context building.
"""
import os
import time

from src.application.infra.client import chat_create, CONTEXT_MODEL
from src.application.infra import token_stats
from src.application.infra.log import log
from src.config.config import load_config

_WINDOW_SYSTEM = """\
You are Mina's present-moment awareness module. Your only input is the live conversation \
window — you see nothing from long-term memory or past sessions.

IMPORTANT — time gaps: The messages below are ordered chronologically but may have large \
time gaps between them. Message N and message N+1 being adjacent does NOT mean they are \
close in time — they may be hours apart. The [Xm ago] / [Xh ago] / [Xd ago] timestamp on \
each user message is ground truth. A 3-hour gap between two messages means the conversation \
may have completely changed topic. Do not narrate across a large time gap as if it were \
continuous. If the most recent messages are on a completely different topic than earlier \
ones, [CONVERSATION RIGHT NOW] should reflect the current topic — not average across the \
whole window.

Output EXACTLY this structure, with these labels on their own lines:

[CONVERSATION RIGHT NOW]
A flowing paragraph covering the live conversational moment and the immediate past through \
the full decoder window. The most recent exchange should be the most vivid and specific — \
closest to now gets the richest detail. Further back in the window gets lighter. Present \
tense for the immediate beat, past tense for what led here. Intentionally overlaps Mina's \
4-message direct window — this overlap is the anchor. Focus on: what was said, what is \
happening, what has been established. If the window is nearly empty, just describe the \
immediate exchange.

Do NOT describe emotional state, mood, affect, or how anything "lands" — the emotion \
module owns that. Situational facts only.

[YOUR PRESENT STATE]
A flowing paragraph grounded in the window. Where is Mina physically? What is she doing? \
What is the immediate situation she is operating in? Active verbs, present tense. Specific \
physical and situational details drawn from the window (location, proximity, activity, \
atmosphere). If the window gives no location context, say she is in her Discord channel.

Do NOT describe how she feels emotionally, her mood, or her internal state. Physical and \
situational facts only: where she is, what she is doing, what is around her.

Hard rules:
- Never write in first person. You are not Mina.
- Never describe emotional state, mood, affect, arousal, or feelings.
- Never describe internal sensations — the chemistry module owns all of that.
- Facts only. Gradient richness: richer near now, lighter for older events.
"""

_RAG_CONTEXT_SYSTEM = """\
You are Mina's long-term memory retrieval module. Your only input is retrieved memory — \
you see nothing from the live conversation window.

Output EXACTLY this structure, with these labels on their own lines:

[RECENT CONTEXT — last 2 hours]
Short paragraph if material exists. Situational facts about what happened recently that \
is relevant to this moment. If nothing qualifies: none.

[SEMI-RECENT CONTEXT — 2 to 24 hours ago]
1–2 sentences. A relevant fact from the last day. If nothing qualifies: none.

[HISTORICAL CONTEXT — more than 24 hours ago]
1 sentence max. Only if it is a dead-ringer match for this specific moment — not just \
thematically adjacent. If nothing qualifies: none.

Hard rules that apply to ALL blocks:
- Never write in first person. You are not Mina.
- Never describe Mina's emotional state, mood, or feelings — the emotion module owns that.
- Never describe Mina's current physical state or sensations.
- Facts only. Gradient richness: richer near now, lighter for history.
"""

_WINDOW_DEFAULT = """\
[YOUR PRESENT STATE]
You are hanging out in your Discord channel, sitting on the couch."""


def build_window_context(
    decoder_window: list[dict],
    username: str,
    user_input: str,
) -> str:
    if not decoder_window:
        return _WINDOW_DEFAULT

    lines = []
    for m in decoder_window:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        content = str(content).strip()
        if not content:
            continue
        ts = m.get("ts")
        label = "USER" if role == "user" else "MINA"
        if ts and role == "user":
            delta = time.time() - ts
            if delta < 120:
                age = "just now"
            elif delta < 3600:
                age = f"{int(delta / 60)}m ago"
            elif delta < 86400:
                age = f"{int(delta / 3600)}h ago"
            else:
                age = f"{int(delta / 86400)}d ago"
            lines.append(f"[{age}] {label}: {content[:400]}")
        else:
            lines.append(f"{label}: {content[:400]}")

    window_text = "\n".join(lines)
    messages = [
        {"role": "system", "content": _WINDOW_SYSTEM},
        {"role": "user", "content": f"[CURRENT MESSAGE FROM {username.upper()}]\n{user_input}\n\n[DECODER WINDOW — most recent last]\n{window_text}"},
    ]

    response = chat_create(
        model=CONTEXT_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=512,
    )
    token_stats.record_response("context_window", response)
    result = (response.choices[0].message.content or "").strip()
    if result:
        log("CONTEXT/WINDOW", result)
    return result


def build_rag_context(
    query: str,
    kag_context: str,
    rag_recent: str,
    rag_semi_recent: str,
    rag_historical: str,
) -> str:
    from src.brain.hippocampus.hippocampus import read_identity

    def _read_file(path: str) -> str:
        try:
            from src.config.config import REPO_ROOT
            with open(os.path.join(REPO_ROOT, path)) as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    customization_files = load_config().get("customization_files", [])
    identity_parts = [p for p in [read_identity("MINA.md")] + [_read_file(f) for f in customization_files] if p]
    identity = "\n\n---\n\n".join(identity_parts)

    has_memory = rag_recent or rag_semi_recent or rag_historical or kag_context
    llm_context = ""
    if has_memory:
        parts = [f"[CURRENT QUERY]\n{query}"]
        if rag_recent:
            parts.append(f"[RETRIEVED MEMORIES — last 2 hours]\n{rag_recent}")
        if rag_semi_recent:
            parts.append(f"[RETRIEVED MEMORIES — 2 to 24 hours ago]\n{rag_semi_recent}")
        if rag_historical:
            parts.append(f"[RETRIEVED MEMORIES — older than 24 hours]\n{rag_historical}")
        if kag_context:
            parts.append(f"[BACKGROUND KNOWLEDGE]\n{kag_context}")

        messages = [
            {"role": "system", "content": _RAG_CONTEXT_SYSTEM},
            {"role": "user", "content": "\n\n---\n\n".join(parts)},
        ]

        response = chat_create(
            model=CONTEXT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=400,
        )
        token_stats.record_response("context_rag", response)
        llm_context = (response.choices[0].message.content or "").strip()
        if llm_context:
            log("CONTEXT/RAG", llm_context)

    out_parts = []
    if identity:
        out_parts.append(identity)
    if llm_context:
        out_parts.append(llm_context)
    return "\n\n---\n\n".join(out_parts)
