"""Bio-triggered memory saves — processes EventBus events after advance().

Called from heartbeat.py and cortex.py after load_and_advance() to decide
whether biological events are significant enough to save to RAG or flag for
KAG synthesis.

RAG_SIGNIFICANCE_THRESHOLD: individual events above this → episodic RAG save
MULTI_EVENT_THRESHOLD:      this many moderate events simultaneously → composite RAG save
KAG_SIGNIFICANCE_THRESHOLD: above this → flag for KAG synthesis in freetime

SPEC-24.
"""
from __future__ import annotations

import json
import os
import time

from src.sim.events import BiologicalEvent, EventBus
from src.sim.bio.state import BiologicalState
from src.sim.constants import (
    ALLOSTATIC_KAG_THRESHOLD,
    KAG_SIGNIFICANCE_THRESHOLD,
    MULTI_EVENT_RAG_COUNT,
    RAG_SIGNIFICANCE_THRESHOLD,
)

MULTI_EVENT_THRESHOLD = MULTI_EVENT_RAG_COUNT  # local alias for backward compat

_KAG_FLAG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "run", "pending_kag_events.json",
)


def process_events(s: BiologicalState, events: list[BiologicalEvent],
                   context_hint: str = "") -> None:
    """
    Process events from advance() and trigger appropriate memory saves.

    Called from heartbeat.py and cortex.py after each advance().
    context_hint: optional string from conversation context
                  (e.g. the user's last message, for richer RAG entries).
    """
    if not events:
        return

    significant    = [e for e in events if e.significance >= RAG_SIGNIFICANCE_THRESHOLD]
    kag_candidates = [e for e in events if e.significance >= KAG_SIGNIFICANCE_THRESHOLD]

    # Rule 1: Any high-significance individual event → RAG save
    for event in kag_candidates:
        text = _format_rag_event(s, event, context_hint)
        try:
            from hippocampus import rag_add
            rag_add(text, metadata={
                "type":      "biological_event",
                "chemical":  event.chemical,
                "system":    event.system,
                "severity":  event.severity,
                "value":     event.value,
                "timestamp": event.timestamp,
            })
        except Exception:
            pass

    # Rule 2: Multiple moderate events simultaneously → composite RAG save
    if len(significant) >= MULTI_EVENT_THRESHOLD and len(significant) > len(kag_candidates):
        text = _format_composite_rag_event(s, significant, context_hint)
        try:
            from hippocampus import rag_add
            rag_add(text, metadata={
                "type":  "biological_composite_event",
                "count": len(significant),
            })
        except Exception:
            pass

    # Rule 3: Flag KAG candidates for freetime synthesis
    if kag_candidates:
        _flag_kag_candidates(s, kag_candidates)

    # Rule 4: Allostatic load milestones → always KAG
    al = s.neuroplasticity.get("allostatic_load", 0.0)
    for ae in events:
        if ae.chemical == "allostatic_load" and ae.label_crossed and al > ALLOSTATIC_KAG_THRESHOLD:
            _flag_kag_allostatic(s, al)


def _format_rag_event(s: BiologicalState, event: BiologicalEvent,
                       context_hint: str) -> str:
    """Format a biological event as a RAG-storable memory fragment."""
    from src.sim.psych.derived import derived
    d  = derived(s)
    so = d["second_order"]
    to = d["third_order"]
    mood_summary = (
        f"energy={so['energy']:.0f}, mood={so['mood_valence']:.0f}, "
        f"anxiety={to['anxiety']:.0f}"
    )
    context_part = f" Context: {context_hint}" if context_hint else ""
    return (
        f"[{event.system.upper()} EVENT] {event.chemical} reached {event.label} "
        f"({event.value:.1f} {event.unit}). Significance: {event.severity}. "
        f"State: {mood_summary}.{context_part}"
    )


def _format_composite_rag_event(s: BiologicalState, events: list[BiologicalEvent],
                                  context_hint: str) -> str:
    from src.sim.psych.derived import derived
    chemicals = ", ".join(f"{e.chemical}={e.label}" for e in events[:5])
    d  = derived(s)
    to = d["third_order"]
    dominant = max(to.items(), key=lambda x: x[1])
    return (
        f"[COMPOUND BIOLOGICAL STATE] Multiple systems activated simultaneously: "
        f"{chemicals}. Dominant emotional state: {dominant[0]} ({dominant[1]:.0f}/100). "
        f"{'Context: ' + context_hint if context_hint else ''}"
    )


def _flag_kag_candidates(s: BiologicalState, events: list[BiologicalEvent]) -> None:
    """Write to pending KAG queue. freetime.py processes this queue."""
    existing: list[dict] = []
    try:
        with open(_KAG_FLAG_FILE) as f:
            existing = json.load(f)
    except Exception:
        pass

    for event in events:
        existing.append({
            "chemical":    event.chemical,
            "system":      event.system,
            "value":       event.value,
            "label":       event.label,
            "significance": event.significance,
            "timestamp":   event.timestamp,
        })

    try:
        os.makedirs(os.path.dirname(_KAG_FLAG_FILE), exist_ok=True)
        with open(_KAG_FLAG_FILE, "w") as f:
            json.dump(existing[-20:], f, indent=2)   # cap at 20 pending
    except Exception:
        pass


def _flag_kag_allostatic(s: BiologicalState, al: float) -> None:
    """Allostatic load milestone — a permanent change in Mina's biology."""
    milestone = "HIGH" if al < 70 else "SEVERE"
    _flag_kag_candidates(s, [BiologicalEvent(
        event_type="threshold_crossed",
        system="psych",
        chemical="allostatic_load",
        value=al,
        delta=0.0,
        unit="AU",
        label=milestone,
        label_crossed=True,
        severity="major",
        significance=0.9,
        timestamp=time.time(),
    )])
