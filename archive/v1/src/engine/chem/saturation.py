"""
Encoder saturation logic — soft_ceiling / hard_ceiling scaling for subconscious deltas.

Soft ceiling: positive deltas are scaled down proportionally as the value approaches the ceiling.
Hard ceiling: positive deltas are blocked entirely above this value.

This is applied in apply_deltas() to prevent runaway encoder hits on the same chemical.
"""
from __future__ import annotations


def apply_saturation(name: str, current: float, delta: float) -> float:
    """
    Apply soft/hard ceiling saturation to a positive encoder delta.
    Negative deltas (suppressions) pass through unmodified.
    Returns the scaled delta.
    """
    if delta <= 0:
        return delta

    from src.engine.chem.registry import REGISTRY
    p = REGISTRY.get(name)
    if not p:
        return delta

    hard = p.hard_ceiling
    soft = p.soft_ceiling

    # Hard ceiling: block positive deltas entirely
    if hard is not None and current >= hard:
        return 0.0

    # Soft ceiling: scale down as value approaches hard ceiling
    if soft is not None and hard is not None and current >= soft:
        # Linear scale: full delta at soft, zero at hard
        scale = max(0.0, (hard - current) / (hard - soft))
        return delta * scale

    return delta
