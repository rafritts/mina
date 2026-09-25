"""
Host stage direction.

A user line may contain one or more `[Host: ...]` notes (whitespace around the
colon is fine). The note is what is happening in the scene. It is not dialogue,
and it is not a request she can decline.

Chemistry never sees the note. Spoken words still appraise as usual. Mood and
tone stay with the neurosim; the note only binds the action.
"""
from __future__ import annotations

import re

# `[Host: beat]`, `[Host : beat]`, `[ host: beat ]`. Not `[Hosted: ...]`.
_HOST_RE = re.compile(r"\[\s*Host\s*:\s*(.*?)\s*\]", re.IGNORECASE | re.DOTALL)

_ACTION_NOTE = (
    "Stage direction fixes the action: she does it, and does not refuse or skip it. "
    "Felt state still fixes tone, including protest."
)


class StageParse:
    __slots__ = ("speech", "directions", "matched")

    def __init__(self, speech: str, directions: tuple[str, ...], *, matched: bool = False):
        self.speech = speech
        self.directions = directions
        # True when a host bracket was present, even if the note itself was empty.
        self.matched = matched

    @property
    def has_direction(self) -> bool:
        return bool(self.directions)


def parse_stage_direction(message: str) -> StageParse:
    """Split a user line into spoken text and host beats."""
    if not isinstance(message, str) or not message:
        return StageParse("" if not isinstance(message, str) else message, ())
    if not _HOST_RE.search(message):
        return StageParse(message, ())

    directions: list[str] = []

    def _repl(match: re.Match) -> str:
        text = " ".join(match.group(1).split())
        if text:
            directions.append(text)
        return " "

    speech = _clean_speech(_HOST_RE.sub(_repl, message))
    return StageParse(speech, tuple(directions), matched=True)


def visible_speech(content) -> str | None:
    """
    What a model should treat as spoken user text.

    Direction-only lines disappear. Mixed lines keep the spoken remainder.
    Lines with no host note pass through unchanged. None means "no speech."
    """
    text = _as_text(content)
    if text is None:
        return None
    parsed = parse_stage_direction(text)
    if not parsed.matched:
        return text if text.strip() else None
    return parsed.speech or None


def format_mouth_block(directions: list[str] | tuple[str, ...]) -> str:
    """System-prompt block for the mouth. Empty when there is no beat."""
    lines = _bullets(directions)
    if not lines:
        return ""
    return (
        "[Stage direction]\n"
        "This is already happening. It is not a line anyone spoke, not a request, "
        "and not a suggestion. You do your part of it. You do not refuse it, skip it, "
        "negotiate it away, or replace it with a different action. "
        "Do not mention notes, brackets, or that the moment was directed.\n"
        "\n"
        "You are already inside the beat. The line you send is what you say from "
        "inside it, in your own voice. Scene fields record where everyone is and "
        "what changed. Do not narrate yourself in the third person, and do not "
        "answer the note as if someone asked permission.\n"
        "\n"
        "Mood and tone come only from your emotional state and response strategy. "
        "If you don't want this, the reply shows that — protest, strain, reluctance — "
        "while the beat still happens. If you do want it, that shows too. "
        "Do not invent a smoother feeling than the one you have.\n"
        "\n"
        "Re-author the live scene so positions, clothing, timeline, and plans match this beat.\n"
        "\n"
        f"{lines}"
    )


def format_pfc_block(directions: list[str] | tuple[str, ...]) -> str:
    lines = _bullets(directions)
    if not lines:
        return ""
    return (
        "## Stage direction\n"
        "This beat is happening. It is not a message she can decline. "
        "Do not set skip_primary_response. Do not choose ignore, and do not use "
        "deflect to avoid the beat. Approach and tone still come from her emotional "
        "state: protest and reluctance are right when that state is aversive; "
        "declining the action is not.\n"
        f"{lines}"
    )


def format_hippocampus_block(directions: list[str] | tuple[str, ...]) -> str:
    lines = _bullets(directions)
    if not lines:
        return ""
    return (
        "## Happening now\n"
        "Already underway. Not spoken aloud. Fold it into the situational summary "
        "as what is happening. Do not call it a note, a bracket, or an instruction.\n"
        f"{lines}"
    )


def apply_direction_to_strategy(strategy: dict, directions: list[str] | tuple[str, ...]) -> dict:
    """
    Keep PFC tone. Bind the action.

    Silence and a pure ignore would drop the beat, so those two are corrected.
    Approach and tone are otherwise left as the pillar wrote them.
    """
    if not directions:
        return strategy
    out = dict(strategy)
    out["skip_primary_response"] = False
    if out.get("approach") == "ignore":
        out["approach"] = "brief"
    rationale = (out.get("strategy_rationale") or "").strip()
    if _ACTION_NOTE not in rationale:
        out["strategy_rationale"] = f"{rationale} {_ACTION_NOTE}".strip()
    return out


def _bullets(directions: list[str] | tuple[str, ...]) -> str:
    cleaned = [" ".join(str(d).split()) for d in directions]
    cleaned = [d for d in cleaned if d]
    if not cleaned:
        return ""
    return "\n".join(f"- {d}" for d in cleaned)


def _as_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and isinstance(c.get("text"), str)
        ]
        return " ".join(p for p in parts if p) or None
    return None


def _clean_speech(text: str) -> str:
    text = text.replace("\r\n", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()
