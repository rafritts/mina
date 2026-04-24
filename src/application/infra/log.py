"""
Unified log helper for Mina.

Output format: [HH:MM:SS] [TAG] message

Tags use UPPER_CASE with / for subcategories (e.g. ENCODER/STIM, BIO/TICK/ERROR).
Import and call log() from any module — no configuration needed.
"""
import json
import re
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[3]
_COMPACT_LOG = _PROJECT_ROOT / "logs" / "mina-compact.log"
_SEP = "─" * 60

# Non-turn tags written directly to mina-compact.log
_COMPACT_TAGS = {
    "MINA",
    "GATEWAY", "GATEWAY/ERROR",
    "FREETIME",
    "FOLLOWUP", "FOLLOWUP/REPLY", "FOLLOWUP/ERR",
    "SEND", "SEND/ERROR",
    "SLEEP",
    "DANGER", "WIPE",
    "BIO/TICK",
}

# Per-turn buffer; flushed as a structured block when MINA is logged
_turn: dict[str, str] = {}


def _compact_bio(profile: str) -> str:
    def val(key: str) -> str:
        m = re.search(rf"^\s*{re.escape(key)}\s+([\d.]+)", profile, re.MULTILINE)
        return m.group(1) if m else "?"

    emotional = (
        f"hedonic:{val('hedonic_tone')} mood:{val('mood_valence')} "
        f"arousal:{val('arousal')} warmth:{val('social_warmth')} "
        f"energy:{val('energy')} clarity:{val('cognitive_clarity')}"
    )
    negative = f"anx:{val('anxiety')} dep:{val('depression')} lone:{val('loneliness')} bore:{val('boredom')}"
    chem = (
        f"da:{val('dopamine')} 5ht:{val('serotonin')} "
        f"na:{val('norepinephrine')} ach:{val('acetylcholine')} "
        f"cort:{val('cortisol')} epi:{val('epinephrine')}"
    )
    return f"{emotional} | {negative} | {chem}"


def _append_compact(text: str) -> None:
    try:
        with open(_COMPACT_LOG, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def _flush_turn(mina_msg: str) -> None:
    parts = []
    if _turn.get("user"):
        parts.append(f"[USER] {_turn['user']}")
    enc_tag = _turn.get("encoder_tag")
    enc_msg = _turn.get("encoder_msg")
    if enc_tag and enc_msg is not None:
        parts.append(f"[{enc_tag}] {enc_msg}")
    if _turn.get("bio"):
        parts.append(f"[BIO/PROFILE] {_compact_bio(_turn['bio'])}")
    if _turn.get("adjudicator"):
        try:
            d = json.loads(_turn["adjudicator"])
            lands = d.get("stimulus_lands_as", "")
            if lands:
                parts.append(f"[HOW IT LANDS] {lands}")
        except (json.JSONDecodeError, ValueError):
            pass
    parts.append(f"[MINA] {mina_msg}")
    parts.append(_SEP)
    _append_compact("\n".join(parts))
    _turn.clear()


def log(tag: str, msg: str = "") -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{tag}] {msg}" if msg else f"[{ts}] [{tag}]"
    print(line, flush=True)

    if tag == "USER":
        _turn.clear()
        _turn["user"] = msg
    elif tag.startswith("ENCODER/") and not any(tag.endswith(s) for s in ("/ERR", "/ERROR", "/RETRY", "/HAB")):
        _turn["encoder_tag"] = tag
        _turn["encoder_msg"] = msg
    elif tag == "BIO/PROFILE":
        _turn["bio"] = msg
    elif tag == "ADJUDICATOR":
        _turn["adjudicator"] = msg
    elif tag == "MINA":
        _flush_turn(msg)
    elif tag in _COMPACT_TAGS:
        _append_compact(f"[{tag}] {msg}" if msg else f"[{tag}]")
