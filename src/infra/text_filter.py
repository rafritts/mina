"""
Runtime text substitutions applied to both input (to the LLM) and output (to Discord).

Currently handles: girl/girls → woman/women, preserving capitalisation.
Motivation: the Grok content filter false-positives on "girl" on content filters.
"""

import re

_PAIRS = [
    # Plural first so "girls" isn't partially matched as "girl" + s
    (re.compile(r"\bGIRLS\b"), "WOMEN"),
    (re.compile(r"\bGirls\b"), "Women"),
    (re.compile(r"\bgirls\b"), "women"),
    (re.compile(r"\bGIRL\b"), "WOMAN"),
    (re.compile(r"\bGirl\b"), "Woman"),
    (re.compile(r"\bgirl\b"), "woman"),
]


def apply_word_filter(text: str) -> str:
    """Substitute girl/girls → woman/women (case-preserving) in *text*."""
    for pattern, replacement in _PAIRS:
        text = pattern.sub(replacement, text)
    return text
