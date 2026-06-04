"""
Sim — the live chemistry simulation.

Owns the ChemicalState, a threading.Lock, and a background thread that runs
tick() every 10 seconds. All external access goes through apply_delta() and
snapshot(). Thread safety is guaranteed by the lock.

Usage:
    sim = Sim()
    sim.start()
    ...
    sim.apply_delta("dopamine", 2.5, source="encoder")
    decoded = sim.snapshot()
    ...
    sim.stop()
"""
from __future__ import annotations

import threading
import time

from src.application.infra.log import log
from src.config.config import SIM_STATE_FILE, load_big5
from .state import ChemicalState
from .tick import tick, build_initial_state
from .decoder import decode

_TICK_INTERVAL_S = 10.0


class Sim:
    def __init__(self) -> None:
        big5 = load_big5()
        try:
            self._state = ChemicalState.load(SIM_STATE_FILE)
            log("SIM", "Loaded persisted state.")
        except (FileNotFoundError, Exception):
            self._state = build_initial_state(big5)
            log("SIM", "Initialized fresh state from params + Big 5.")

        self._big5: dict[str, float] = big5
        self._lock  = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sleeping = False

    # ── Public API ─────────────────────────────────────────────────────────

    def apply_delta(self, chemical: str, magnitude_nM: float, source: str = "") -> None:
        """
        Apply an external delta to a chemical's phasic level.
        This is the single external entry point for all chemistry inputs —
        encoder outputs, tool-driven (eat/drink), FREETIME actions.
        """
        with self._lock:
            lvl = self._state.levels.get(chemical)
            if lvl is None:
                return
            lvl.phasic = max(0.0, lvl.phasic + magnitude_nM)

    def apply_chemistry_from_encoder(
        self,
        encoder_output: dict,
        relationship_modifier: float = 1.0,
    ) -> None:
        """Run the chemistry function against encoder output, applying Class 1 deltas."""
        from .chemistry import apply_chemistry
        with self._lock:
            apply_chemistry(encoder_output, self._state, self._big5, relationship_modifier)

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Return the current decoder output (thread-safe snapshot)."""
        with self._lock:
            return decode(self._state)

    def get_big5(self) -> dict[str, float]:
        return dict(self._big5)

    def set_sleeping(self, sleeping: bool) -> None:
        with self._lock:
            self._sleeping = sleeping

    def save(self) -> None:
        with self._lock:
            self._state.save(SIM_STATE_FILE)

    # ── Background tick thread ─────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._tick_loop, daemon=True, name="sim-tick")
        self._thread.start()
        log("SIM", f"Tick thread started (interval={_TICK_INTERVAL_S}s).")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        self.save()
        log("SIM", "Tick thread stopped; state saved.")

    def _tick_loop(self) -> None:
        last_tick = time.time()
        save_counter = 0
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_TICK_INTERVAL_S)
            now = time.time()
            dt  = now - last_tick
            last_tick = now

            with self._lock:
                tick(self._state, dt, sleeping=self._sleeping)

            save_counter += 1
            if save_counter >= 18:  # save every ~3 minutes
                self.save()
                save_counter = 0
