"""Shared fixtures for src.engine subsystem tests."""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.engine.bio.state import BiologicalState
from src.engine.bio.defaults import chemical_defaults, neuroendocrine_defaults


def make_state(**overrides) -> BiologicalState:
    """Create a clean BiologicalState with optional field overrides.

    Overrides are resolved by checking each tier in order:
    chemicals → neuroendocrine → immune → pain → body → neuroplasticity
    """
    s = BiologicalState()
    for k, v in overrides.items():
        if k in s.chemicals:
            s.chemicals[k] = float(v)
        elif k in s.neuroendocrine:
            s.neuroendocrine[k] = float(v)
        elif k in s.immune:
            s.immune[k] = float(v)
        elif k in s.pain:
            s.pain[k] = float(v)
        elif k in s.body:
            s.body[k] = float(v)
        elif k in s.neuroplasticity:
            s.neuroplasticity[k] = float(v)
    return s
