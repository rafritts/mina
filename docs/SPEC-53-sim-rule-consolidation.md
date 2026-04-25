# SPEC-53: Simulation Rule Consolidation

**Status: FLAG — not yet specced**

## Problem

Chemical behavior is fragmented across multiple files that don't agree with each other:
`registry.py`, `engine.py`, `constants.py`, `derived.py`, `decoder.py`. A question like
"how does cortisol actually behave?" requires reading five files. The epinephrine half-life
bug (49-minute effective half-life from a mismatched comment and formula) is a direct product
of this fragmentation.

## Intent

Make `ChemicalProfile` in the registry the single source of truth for each chemical's complete
lifecycle: decay type, half-life, threshold-triggered notes, and causal surfacing. The engine
becomes a generic executor. Threshold rules and bio report notes (currently `INTERACTION_RULES`
in `decoder.py`) consolidate into the registry or a single dedicated `rules.py`.

## Not yet designed
