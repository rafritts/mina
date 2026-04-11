"""
Mina's observations — a single living document.

The observations are working memory, not a feelings log. Completely replaced each
time the subconscious runs. They capture the cognitive/intentional layer: what she's
thinking about, what she wants to do, what's unresolved, what she noticed, what she's
planning. Present tense, first person, 3–6 sentences.

The biological report encodes how she feels. This encodes what's on her mind.

File: run/monologue.md
"""
import os

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_MONOLOGUE_FILE = os.path.join(_PROJECT_ROOT, "run", "monologue.md")


def read() -> str:
    """Return the current observations text, or empty string if none exists."""
    try:
        with open(_MONOLOGUE_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write(text: str) -> None:
    """Replace the entire observations with new text."""
    os.makedirs(os.path.dirname(_MONOLOGUE_FILE), exist_ok=True)
    with open(_MONOLOGUE_FILE, "w") as f:
        f.write(text.strip())
