"""Normalization, label lookup, and clamping utilities for chemical values."""
from __future__ import annotations


def normalize(name: str, value: float) -> float:
    """Return 0.0–1.0 bar chart position. Clamps outside display range."""
    from src.engine.chem.registry import REGISTRY
    p = REGISTRY.get(name)
    if not p or p.display_max == p.display_min:
        return 0.0
    return max(0.0, min(1.0, (value - p.display_min) / (p.display_max - p.display_min)))


def get_label_with_depth(name: str, value: float) -> tuple[str, str, float]:
    """
    Return (label_name, implication, depth_in_label).
    depth: 0.0 = just entered this label, 1.0 = at its ceiling.
    """
    from src.engine.chem.registry import REGISTRY
    p = REGISTRY.get(name)
    if not p or not p.labels:
        return ("—", "", 0.0)
    prev_upper = p.display_min
    for upper, label, impl in p.labels:
        if value < upper:
            span = upper - prev_upper
            depth = round((value - prev_upper) / span, 2) if span > 0 else 0.0
            return label, impl, min(1.0, max(0.0, depth))
        prev_upper = upper
    last = p.labels[-1]
    return last[1], last[2], 1.0


def get_label(name: str, value: float) -> tuple[str, str]:
    """Return (label_name, implication) for value from the chemical's label table."""
    label, impl, _ = get_label_with_depth(name, value)
    return label, impl


def clamp_chemical(name: str, value: float) -> float:
    """Clamp a chemical value to [0, critical_high]."""
    from src.engine.chem.registry import REGISTRY
    p = REGISTRY.get(name)
    if not p:
        return max(0.0, value)
    hi = p.critical_high if p.critical_high > 0 else p.display_max * 2
    return max(0.0, min(hi, value))
