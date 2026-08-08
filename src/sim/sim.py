"""
Sim — the live chemistry simulation.

Owns the ChemicalState, a threading.Lock, and a background thread that runs
tick() every 10 seconds. All external access goes through apply_delta() and
snapshot(). Thread safety is guaranteed by the lock.

Auto-sleep: when adenosine exceeds SLEEP_ENTER_ADENOSINE the sim enters sleep
and clears sleep pressure until SLEEP_WAKE_ADENOSINE (after a minimum duration).
This closes the wake-pressure → monoamine-collapse loop that had no sink.
"""
from __future__ import annotations

import threading
import time

from src.application.infra.log import log
from src.config.config import SIM_STATE_FILE, load_big5
from .state import ChemicalState
from .tick import tick, build_initial_state, chemical_norm, biased_natural_setpoint
from .decoder import decode
from .observer import Observer
from .params import (
    CHEMICAL_PARAMS,
    CIRCADIAN,
    SLEEP_ENTER_ADENOSINE,
    SLEEP_WAKE_ADENOSINE,
    SLEEP_MIN_DURATION_S,
    SETPOINT_FLOOR_FRAC,
    OPPONENT_TONIC_FLOOR_FRAC,
    CHEMICAL_TOTAL_CAP_MULT,
)

_TICK_INTERVAL_S = 10.0
# Circadian setpoints outside this band of Big5-biased natural are treated as
# multi-day clock-ratchet scars (SPEC-62 DEFECT-1).
_CIRCADIAN_SETPOINT_SCAR_FRAC = 0.25


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
        self._repair_collapsed_setpoints()
        self._repair_circadian_setpoint_scars()
        self._lock  = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Restore sleep from persisted state (SPEC-62 DEFECT-2)
        self._sleeping = bool(self._state.sleeping)
        self._sleep_elapsed_s = float(self._state.sleep_elapsed_s)
        self._observer = Observer()
        # If restored asleep without an onset stamp, stamp now so UI has something.
        if self._sleeping and self._state.sleep_started_at is None:
            now = time.time()
            # Prefer reconstructing from elapsed so "asleep since" is honest.
            if self._sleep_elapsed_s > 0:
                self._state.sleep_started_at = now - self._sleep_elapsed_s
            else:
                self._state.sleep_started_at = now
            if self._state.last_sleep_started_at is None:
                self._state.last_sleep_started_at = self._state.sleep_started_at

    # ── Public API ─────────────────────────────────────────────────────────

    def apply_delta(self, chemical: str, magnitude_nM: float, source: str = "") -> None:
        """
        Apply an external delta to a chemical's phasic level.
        This is the single external entry point for all chemistry inputs —
        encoder outputs, tool-driven (eat/drink), FREETIME actions.
        """
        with self._lock:
            lvl = self._state.levels.get(chemical)
            p = CHEMICAL_PARAMS.get(chemical)
            if lvl is None or p is None:
                return
            lvl.phasic = max(0.0, lvl.phasic + magnitude_nM)
            max_total = p["normalization_max"] * CHEMICAL_TOTAL_CAP_MULT
            excess = (lvl.tonic + lvl.phasic) - max_total
            if excess > 0:
                lvl.phasic = max(0.0, lvl.phasic - excess)

    def apply_chemistry_from_encoder(
        self,
        encoder_output: dict,
        relationship_modifier: float = 1.0,
    ) -> dict[str, float]:
        """Run the chemistry function against encoder output, applying Class 1 deltas.

        Returns {chemical: delta_nM} for non-trivial applications (may be empty).
        """
        from .chemistry import apply_chemistry
        with self._lock:
            return apply_chemistry(
                encoder_output, self._state, self._big5, relationship_modifier
            )

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Return the current decoder output (thread-safe snapshot)."""
        with self._lock:
            return decode(self._state)

    def get_big5(self) -> dict[str, float]:
        return dict(self._big5)

    def is_sleeping(self) -> bool:
        with self._lock:
            return self._sleeping

    def set_sleeping(self, sleeping: bool) -> None:
        with self._lock:
            if sleeping and not self._sleeping:
                self._enter_sleep_locked(source="external")
            elif not sleeping and self._sleeping:
                self._exit_sleep_locked(source="external")

    def _enter_sleep_locked(self, source: str = "auto") -> None:
        """Mark sleep onset. Caller holds the lock."""
        now = time.time()
        self._sleeping = True
        self._sleep_elapsed_s = 0.0
        self._state.sleep_started_at = now
        self._state.last_sleep_started_at = now
        self._sync_sleep_to_state()
        log("SIM", f"Sleep ON ({source}).")
        try:
            from src.application.infra.events import emit as emit_event
            emit_event(
                "activity",
                f"Went to sleep ({source})",
                {"source": "sleep", "sleeping": True, "sleep_started_at": now},
            )
        except Exception:
            pass

    def _exit_sleep_locked(self, source: str = "auto") -> None:
        """Mark wake. Caller holds the lock."""
        now = time.time()
        started = self._state.sleep_started_at or self._state.last_sleep_started_at
        self._sleeping = False
        self._sleep_elapsed_s = 0.0
        self._state.sleep_started_at = None
        self._state.last_woke_at = now
        self._sync_sleep_to_state()
        log("SIM", f"Sleep OFF ({source}).")
        try:
            from src.application.infra.events import emit as emit_event
            duration = (now - started) if started else None
            label = "Woke up"
            if duration and duration > 0:
                hours = duration / 3600.0
                label = f"Woke up after {hours:.1f}h ({source})"
            else:
                label = f"Woke up ({source})"
            emit_event(
                "activity",
                label,
                {
                    "source": "sleep",
                    "sleeping": False,
                    "last_sleep_started_at": started,
                    "last_woke_at": now,
                    "duration_s": duration,
                },
            )
        except Exception:
            pass

    def _sync_sleep_to_state(self) -> None:
        """Write sleep fields through to ChemicalState for persistence."""
        self._state.sleeping = self._sleeping
        self._state.sleep_elapsed_s = self._sleep_elapsed_s

    def _repair_collapsed_setpoints(self) -> None:
        """
        Restore setpoints/tonics crushed by the old opponent-floor ratchet
        (25% floors) back toward natural baselines.
        """
        repaired = []
        for name, lvl in self._state.levels.items():
            p = CHEMICAL_PARAMS.get(name)
            if not p:
                continue
            natural = p["tonic_setpoint"]
            min_sp = natural * SETPOINT_FLOOR_FRAC
            # Anything below the new floor was a death-spiral scar — restore fully.
            if lvl.setpoint < min_sp - 1e-12:
                lvl.setpoint = natural
                repaired.append(name)
            # Lift tonic at least to the opponent floor so Phase 2 can recover.
            floor = natural * OPPONENT_TONIC_FLOOR_FRAC
            if lvl.tonic < floor:
                lvl.tonic = floor
                if name not in repaired:
                    repaired.append(name)
            # Cap insane phasic (e.g. OT runaway from pre-cap builds)
            max_total = p["normalization_max"] * CHEMICAL_TOTAL_CAP_MULT
            excess = (lvl.tonic + lvl.phasic) - max_total
            if excess > 0:
                lvl.phasic = max(0.0, lvl.phasic - excess)
                if name not in repaired:
                    repaired.append(name)
        if repaired:
            log("SIM", f"Repaired collapsed / overshoot state: {', '.join(repaired)}")

    def _repair_circadian_setpoint_scars(self) -> None:
        """
        Reset circadian-driven setpoints that drifted from multi-day clock
        leakage into allostasis (SPEC-62 DEFECT-1). Monoamines outside
        CIRCADIAN are left alone.
        """
        repaired = []
        for name in CIRCADIAN:
            lvl = self._state.levels.get(name)
            p = CHEMICAL_PARAMS.get(name)
            if not lvl or not p:
                continue
            natural = biased_natural_setpoint(name, self._big5)
            if natural <= 0:
                continue
            rel = abs(lvl.setpoint - natural) / natural
            if rel <= _CIRCADIAN_SETPOINT_SCAR_FRAC:
                continue
            # Outside ±25% of Big5-biased natural → reset allostatic setpoint.
            lvl.setpoint = natural
            repaired.append(f"{name}→{natural:.2f}")
        if repaired:
            log("SIM", f"Repaired circadian setpoint scars: {', '.join(repaired)}")

    def set_chemical(self, chemical: str, tonic_nM: float) -> bool:
        """Set a chemical's tonic level directly (admin override)."""
        with self._lock:
            lvl = self._state.levels.get(chemical)
            if lvl is None:
                return False
            lvl.tonic = max(0.0, tonic_nM)
            lvl.phasic = 0.0
            return True

    def reset_to_baseline(self) -> dict[str, float]:
        """
        Full chemistry reset to natural Big-5-biased baselines.

        Clears phasic reservoirs, restores setpoints/tonics/sensitivity,
        wakes her if sleeping, and persists immediately. Does not wipe
        conversation history or RAG — chemistry only.
        """
        with self._lock:
            self._state = build_initial_state(self._big5)
            self._sleeping = False
            self._sleep_elapsed_s = 0.0
            self._state.sleep_started_at = None
            # Keep last_sleep_* cleared on full chemistry reset — baseline is a fresh day.
            self._state.last_sleep_started_at = None
            self._state.last_woke_at = None
            self._sync_sleep_to_state()
            self._observer = Observer()
            self._state.save(SIM_STATE_FILE)
            norms = {
                name: round(chemical_norm(self._state, name), 2)
                for name in CHEMICAL_PARAMS
                if CHEMICAL_PARAMS[name]["class"] != 4
            }
        log("SIM", "Reset to baseline (awake).")
        return norms

    def advance(self, hours: float) -> None:
        """Fast-forward the simulation by the given number of hours (stepped ticks)."""
        steps = max(1, int(hours * 3600.0 / _TICK_INTERVAL_S))
        with self._lock:
            for _ in range(steps):
                self._maybe_toggle_sleep_locked(_TICK_INTERVAL_S)
                tick(self._state, _TICK_INTERVAL_S, sleeping=self._sleeping)

    def raw_snapshot(self) -> tuple[dict, bool]:
        """Return (levels_dict, sleeping) without decoder side-effects."""
        with self._lock:
            levels = {
                name: {
                    "tonic":       lvl.tonic,
                    "phasic":      lvl.phasic,
                    "setpoint":    lvl.setpoint,
                    "sensitivity": lvl.sensitivity,
                }
                for name, lvl in self._state.levels.items()
            }
            return levels, self._sleeping

    def sleep_info(self) -> dict:
        """Sleep flags + onset timestamps for UI/API."""
        with self._lock:
            return {
                "sleeping": self._sleeping,
                "sleep_elapsed_s": self._sleep_elapsed_s,
                "sleep_started_at": self._state.sleep_started_at,
                "last_sleep_started_at": self._state.last_sleep_started_at,
                "last_woke_at": self._state.last_woke_at,
            }

    def save(self) -> None:
        with self._lock:
            self._state.save(SIM_STATE_FILE)

    # ── Auto-sleep ─────────────────────────────────────────────────────────

    def _maybe_toggle_sleep_locked(self, dt: float) -> None:
        """Enter/exit sleep based on adenosine. Caller holds the lock."""
        ade = chemical_norm(self._state, "adenosine")
        if not self._sleeping and ade >= SLEEP_ENTER_ADENOSINE:
            self._enter_sleep_locked(source=f"auto adenosine={ade:.1f}")
        elif self._sleeping:
            self._sleep_elapsed_s += dt
            if (
                self._sleep_elapsed_s >= SLEEP_MIN_DURATION_S
                and ade <= SLEEP_WAKE_ADENOSINE
            ):
                self._exit_sleep_locked(source=f"auto adenosine={ade:.1f}")
            else:
                # Persist elapsed progress across restarts
                self._sync_sleep_to_state()

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
            # Clamp absurd dt after suspend/resume so one tick cannot jump hours
            dt = min(dt, 60.0)

            with self._lock:
                self._maybe_toggle_sleep_locked(dt)
                tick(self._state, dt, sleeping=self._sleeping)
                self._observer.observe(self._state, dt, self._sleeping)

            save_counter += 1
            if save_counter >= 18:  # save every ~3 minutes
                self.save()
                save_counter = 0
