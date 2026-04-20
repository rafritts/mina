"""
Parse logs/mina.log and write a tightly condensed logs/mina-compact.log.

Each turn becomes:
  [USER] user: message1 / message2 / message3   (all messages in the batch)
  [ENCODER/STIMULUS] deltas — description
  [BIO/PROFILE] hedonic:X mood:X arousal:X warmth:X energy:X clarity:X | anx:X dep:X lone:X bore:X | da:X 5ht:X na:X ach:X cort:X epi:X
  [HOW IT LANDS] one-line from adjudicator stimulus_lands_as
  [MINA] response

Rescued turns (START without END) are included when they have a Mina response,
labelled [RESCUED] so the race condition is visible.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC_LOG = ROOT / "logs" / "mina.log"
DST_LOG = ROOT / "logs" / "mina-compact.log"

# ── helpers ─────────────────────────────────────────────────────────────────

def _val(text: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}\s+([\d.]+)", text, re.MULTILINE)
    return m.group(1) if m else "?"


def _compact_bio(bio_block: str) -> str:
    e = lambda k: _val(bio_block, k)
    emotional = (
        f"hedonic:{e('hedonic_tone')} mood:{e('mood_valence')} "
        f"arousal:{e('arousal')} warmth:{e('social_warmth')} "
        f"energy:{e('energy')} clarity:{e('cognitive_clarity')}"
    )
    negative = (
        f"anx:{e('anxiety')} dep:{e('depression')} "
        f"lone:{e('loneliness')} bore:{e('boredom')}"
    )
    chem = (
        f"da:{e('dopamine')} 5ht:{e('serotonin')} "
        f"na:{e('norepinephrine')} ach:{e('acetylcholine')} "
        f"cort:{e('cortisol')} epi:{e('epinephrine')}"
    )
    return f"{emotional} | {negative} | {chem}"


def _compact_adjudicator(adj_block: str) -> str:
    json_str = re.sub(r"^\[.*?\]\s*\[ADJUDICATOR\]\s*", "", adj_block, flags=re.DOTALL).strip()
    try:
        data = json.loads(json_str)
        return data.get("stimulus_lands_as", json_str[:120])
    except json.JSONDecodeError:
        m = re.search(r'"stimulus_lands_as"\s*:\s*"([^"]+)"', json_str)
        return m.group(1) if m else json_str[:120]


# ── parser ───────────────────────────────────────────────────────────────────

TURN_START = re.compile(r"^={10,}MESSAGE START={10,}$")
TURN_END   = re.compile(r"^={10,}MESSAGE END={10,}$")
TAG_LINE   = re.compile(r"^\[[\d:]+\]\s+\[([^\]]+)\]\s*(.*)")

# Matches the "username: text" lines that appear in rescued multi-message USER blocks
MSG_LINE = re.compile(r"^\w[\w.]*:\s*(.*)")


def _extract_user_messages(user_raw: str) -> str:
    """
    USER blocks in rescued turns look like:
      [HH:MM:SS] [USER] username: first message
      username: second message
      username: third message

    Return all messages joined with ' / '.
    """
    lines = user_raw.splitlines()
    messages = []

    # First line has the timestamp tag
    first = TAG_LINE.match(lines[0])
    if first:
        messages.append(first.group(2).strip())

    # Subsequent lines are raw "username: message" continuations
    for line in lines[1:]:
        m = MSG_LINE.match(line.strip())
        if m:
            messages.append(m.group(1).strip())
        elif line.strip():
            messages.append(line.strip())

    return " / ".join(m for m in messages if m)


def _split_turns(text: str) -> list[tuple[list[str], bool]]:
    """
    Split the log into raw turn blocks.
    Returns list of (lines, completed) where completed=True means MESSAGE END was seen.
    A new MESSAGE START inside an open turn closes the previous one as incomplete.
    """
    turns: list[tuple[list[str], bool]] = []
    current: list[str] = []
    in_turn = False

    for line in text.splitlines():
        stripped = line.strip()
        if TURN_START.match(stripped):
            if in_turn and current:
                turns.append((current, False))
            current = []
            in_turn = True
        elif TURN_END.match(stripped):
            if in_turn:
                turns.append((current, True))
            current = []
            in_turn = False
        elif in_turn:
            current.append(line)

    if in_turn and current:
        turns.append((current, False))

    return turns


def parse_turn_block(lines: list[str], completed: bool) -> dict | None:
    fields: dict[str, list[str]] = {}
    current_tag: str | None = None
    current_buf: list[str] = []

    def flush():
        if current_tag is not None:
            fields.setdefault(current_tag, []).append("\n".join(current_buf))

    for line in lines:
        m = TAG_LINE.match(line)
        if m:
            flush()
            current_tag = m.group(1)
            current_buf = [line]
        else:
            if current_tag is not None:
                current_buf.append(line)

    flush()

    def first(tag: str) -> str:
        return fields.get(tag, [""])[0]

    # USER — capture all batched messages
    user_raw = first("USER")
    user_line = _extract_user_messages(user_raw) if user_raw else ""

    # ENCODER/STIMULUS — first line only
    enc_raw = first("ENCODER/STIMULUS")
    enc_m = TAG_LINE.match(enc_raw.splitlines()[0]) if enc_raw else None
    enc_line = enc_m.group(2) if enc_m else ""

    # BIO/PROFILE
    bio_raw = first("BIO/PROFILE")
    bio_compact = _compact_bio(bio_raw) if bio_raw else ""

    # ADJUDICATOR
    adj_raw = first("ADJUDICATOR")
    how_it_lands = _compact_adjudicator(adj_raw) if adj_raw else ""

    # MINA
    mina_raw = first("MINA")
    mina_m = TAG_LINE.match(mina_raw.splitlines()[0]) if mina_raw else None
    mina_line = mina_m.group(2) if mina_m else ""

    # Drop turns with no meaningful content
    if not user_line and not mina_line:
        return None

    return {
        "user": user_line,
        "encoder": enc_line,
        "bio": bio_compact,
        "lands": how_it_lands,
        "mina": mina_line,
        "rescued": not completed,
    }


# ── formatter ────────────────────────────────────────────────────────────────

def format_turn(t: dict) -> str:
    parts = []
    user_label = "[RESCUED][USER]" if t["rescued"] else "[USER]"
    if t["user"]:
        parts.append(f"{user_label} {t['user']}")
    if t["encoder"]:
        parts.append(f"[ENCODER/STIMULUS] {t['encoder']}")
    if t["bio"]:
        parts.append(f"[BIO/PROFILE] {t['bio']}")
    if t["lands"]:
        parts.append(f"[HOW IT LANDS] {t['lands']}")
    if t["mina"]:
        parts.append(f"[MINA] {t['mina']}")
    return "\n".join(parts)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC_LOG
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DST_LOG

    if not src.exists():
        print(f"Source log not found: {src}", file=sys.stderr)
        sys.exit(1)

    text = src.read_text(encoding="utf-8")
    raw_turns = _split_turns(text)
    turns = [t for raw, completed in raw_turns if (t := parse_turn_block(raw, completed))]

    output_lines = []
    sep = "─" * 60
    for i, t in enumerate(turns):
        if i > 0:
            output_lines.append(sep)
        output_lines.append(format_turn(t))

    dst.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    rescued = sum(1 for t in turns if t["rescued"])
    print(f"Compacted {len(turns)} turns ({rescued} rescued) → {dst}")


if __name__ == "__main__":
    main()
