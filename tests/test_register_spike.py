"""A live breakup must move adrenaline. A stranger cold-open must not."""

from src.sim.chemistry import apply_chemistry, stake_probability
from src.sim.decoder import decode
from src.sim.tick import build_initial_state

BIG5 = {
    "openness": 72.0,
    "conscientiousness": 30.0,
    "extraversion": 48.0,
    "agreeableness": 82.0,
    "neuroticism": 65.0,
}

# Encoder readout from the breakup turn (ui mind snapshot).
BREAKUP = {
    "salience": 9,
    "threat": 1,
    "social_threat": 9,
    "reward": 0,
    "bonding": 0,
    "arousal": 8,
    "aversion": 4,
    "novelty": 7,
    "loss": 9,
    "romance": 0,
    "shame": 6,
    "expected_magnitude": 9,
    "directed_at_mina": True,
    "register_shift": True,
    "channel": "dialogue",
}


def _gap(state, name: str) -> int:
    return decode(state)[name]["gap"]


def test_stake_probability_rises_with_the_live_window():
    assert stake_probability(0.1, 1) == 0.1
    assert stake_probability(0.1, 13) >= 0.8
    assert stake_probability(1.0, 1) == 1.0


def test_breakup_in_a_live_talk_spikes_adrenaline():
    state = build_initial_state(BIG5)
    # Relationship file was empty, so the prior is the stranger floor.
    apply_chemistry(BREAKUP, state, BIG5, relationship_modifier=0.1, turn_depth=20)
    assert _gap(state, "epinephrine") >= 4
    assert _gap(state, "norepinephrine") >= 3


def test_same_breakup_as_a_cold_open_does_not_spike():
    state = build_initial_state(BIG5)
    apply_chemistry(BREAKUP, state, BIG5, relationship_modifier=0.1, turn_depth=1)
    assert _gap(state, "epinephrine") == 0
    assert _gap(state, "norepinephrine") <= 1
