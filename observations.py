"""
Mina's observations — a single living document.

The observations are working memory, not a feelings log. Completely replaced each
time the subconscious runs. They capture the cognitive/intentional layer: what she's
thinking about, what she wants to do, what's unresolved, what she noticed, what she's
planning. Present tense, first person, 3–6 sentences.

The biological report encodes how she feels. This encodes what's on her mind.

File: run/observations.md
"""
import os
from config import OBSERVATIONS_FILE


def read() -> str:
    """Return the current observations text, or empty string if none exists."""
    try:
        with open(OBSERVATIONS_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write(text: str) -> None:
    """Replace the entire observations with new text."""
    os.makedirs(os.path.dirname(OBSERVATIONS_FILE), exist_ok=True)
    with open(OBSERVATIONS_FILE, "w") as f:
        f.write(text.strip())
