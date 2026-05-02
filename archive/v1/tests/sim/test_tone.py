"""
Integration tests for Mina's conversational tone.

Each test runs a full sim scenario from a clean factory-reset state, parses
the resulting log, and grades behavior via LLM. A FAIL verdict fails the test.

These are slow (~2 min per scenario, live LLM required). Run explicitly:

    uv run pytest tests/sim/test_tone.py -m integration -v
    uv run pytest tests/sim/test_tone.py -m integration -k aggressive_flirt -v
"""
import pytest

from scripts.validate import SCENARIOS, run_scenario, grade_scenario


@pytest.mark.integration
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_tone(scenario):
    turns = run_scenario(scenario, do_reset=True)
    assert turns, f"[{scenario.name}] sim produced no output — check mina.log"

    grade = grade_scenario(scenario, turns)
    assert grade.verdict != "FAIL", (
        f"[{scenario.name}] FAIL (confidence {grade.confidence}/10)\n\n"
        f"{grade.reasoning}\n\n"
        + "\n".join(f"  turn {i+1}: {n}" for i, n in enumerate(grade.per_turn_notes))
    )
