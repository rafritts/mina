"""
Somatic narrative — LLM-driven felt-sense description of Mina's physical state.
Input: normalized 0-10 snapshot with resting refs and trend lines.
No raw units, no labels, no rules. The LLM derives the experience from the numbers.
"""
import re

from src.application.infra.client import chat_create, CONTEXT_MODEL
from src.application.infra import token_stats

_SOMATIC_SYSTEM = """\
You are reading a normalized biological snapshot and writing what the body is physically \
experiencing right now — in 2 to 4 sentences.

The numbers are on a 0–10 scale. The resting reference in parentheses is the baseline \
for a healthy, unstressed body. Distance from resting is what matters.

Rules:
- No chemical names. No units. No numbers.
- If all values are near their resting reference, the body is unremarkable — say so in \
one plain sentence and stop. Do not invent fog, fatigue, or unease that the numbers do not show.
- Only when a value is meaningfully above or below its resting reference does it warrant \
a sentence. When you do name a sensation, name its source (e.g. "mouth dry from needing water", \
not just "mouth dry") — but only if the sensation is actually present in the numbers.
- Describe the whole experience, not a list of parts. If multiple signals interact, \
describe that interaction.
- Plain prose only. No preamble. No markdown. No headers.
- Bodyward language preferred: "heart racing", "limbs heavy", "throat tight" rather than \
"I feel X"."""


def build_somatic_narrative(profile_text: str) -> str:
    """
    Generate felt-sense somatic prose from the normalized biological snapshot.
    Called from _build_emotional_profile() with the profile built so far (no somatic yet).
    Returns empty string on failure.
    """
    if not profile_text:
        return ""

    messages = [
        {"role": "system", "content": _SOMATIC_SYSTEM},
        {"role": "user", "content": profile_text},
    ]

    try:
        response = chat_create(
            model=CONTEXT_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=200,
        )
        token_stats.record_response("somatic", response)
        result = (response.choices[0].message.content or "").strip()
        result = re.sub(r"^```\w*\s*", "", result, flags=re.MULTILINE)
        result = re.sub(r"\s*```$", "", result, flags=re.MULTILINE).strip()
        return result
    except Exception:
        return ""
