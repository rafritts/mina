"""
Mina's inner monologue — a single living document.

The monologue is working memory, not a log. Completely replaced each time the
subconscious runs. It captures her current state of mind: what she's feeling,
wanting, fixating on, suppressing. Present tense, first person, 3–6 sentences,
grounded in the biological report.

File: run/monologue.md
"""
import os

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_MONOLOGUE_FILE = os.path.join(_PROJECT_ROOT, "run", "monologue.md")


def read() -> str:
    """Return the current monologue text, or empty string if none exists."""
    try:
        with open(_MONOLOGUE_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write(text: str) -> None:
    """Replace the entire monologue with new text."""
    os.makedirs(os.path.dirname(_MONOLOGUE_FILE), exist_ok=True)
    with open(_MONOLOGUE_FILE, "w") as f:
        f.write(text.strip())
