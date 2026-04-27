"""
Decoder — public surface for the pre-response pipeline.

Submodules:
  application/tools/bio_report.py  biological_report(), needs_summary(), format_state_block()
  somatic.py           LLM-driven somatic narrative
  profile.py           _build_emotional_profile(), normalization, isolation context
  context_assembly.py  build_window_context(), build_rag_context()
  snapshot_history.py  bio snapshot I/O
"""
import time

from src.application.tools.bio_report import (
    biological_report,
    needs_summary,
    format_state_block,
)
from src.brain.subconscious.context_assembly import (
    build_window_context,
    build_rag_context,
)
from src.brain.subconscious.profile import (
    _build_emotional_profile,
    _build_isolation_context,
    _NORM_SCALE,
    _get_chem_val,
)
from src.brain.subconscious.snapshot_history import (
    save_bio_snapshot as _save_bio_snapshot,
    load_bio_snapshots as _load_bio_snapshots,
)

__all__ = [
    "biological_report",
    "needs_summary",
    "format_state_block",
    "build_window_context",
    "build_rag_context",
    "_build_emotional_profile",
    "_build_isolation_context",
    "_save_bio_snapshot",
    "_load_bio_snapshots",
    "_NORM_SCALE",
    "_get_chem_val",
    "_rel_time",
]


def _rel_time(ts: float) -> str:
    delta = time.time() - ts
    if delta < 120:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    days = int(delta / 86400)
    if days < 7:
        return f"{days}d ago"
    return time.strftime("%-d %b", time.localtime(ts))
