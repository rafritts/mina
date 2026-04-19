"""Compatibility shim — imports forwarded to src.sim.chem.*

Existing callers continue to import REGISTRY, ChemicalProfile, Interaction,
normalize, get_label, and clamp_chemical from this module unchanged.
"""
from src.sim.chem.registry import REGISTRY
from src.sim.chem.profiles import ChemicalProfile, Interaction
from src.sim.chem.units import normalize, get_label, clamp_chemical

__all__ = [
    "REGISTRY",
    "ChemicalProfile",
    "Interaction",
    "normalize",
    "get_label",
    "clamp_chemical",
]
