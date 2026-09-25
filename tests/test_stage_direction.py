"""Host stage direction — parse, strip, and strategy bind. No LLM."""
from __future__ import annotations

from src.brain.context_assembly import _format_window
from src.brain.encoder import _format_history
from src.brain.stage_direction import (
    apply_direction_to_strategy,
    format_hippocampus_block,
    format_mouth_block,
    format_pfc_block,
    parse_stage_direction,
    visible_speech,
)
from src.hippocampus.hippocampus import _format_conversation_block


def test_plain_line_is_untouched():
    raw = "  hey, you around?  "
    parsed = parse_stage_direction(raw)
    assert parsed.speech == raw
    assert parsed.directions == ()
    assert parsed.matched is False
    assert visible_speech(raw) == raw


def test_host_brackets_with_optional_space():
    spaced = parse_stage_direction("[Host : she stays where she is]")
    tight = parse_stage_direction("[Host: she stays where she is]")
    padded = parse_stage_direction("[ host : she stays where she is ]")
    for parsed in (spaced, tight, padded):
        assert parsed.matched is True
        assert parsed.speech == ""
        assert parsed.directions == ("she stays where she is",)
        assert visible_speech("[Host : she stays where she is]") is None


def test_speech_and_direction_split():
    parsed = parse_stage_direction("wait [Host: she turns toward the window] what?")
    assert parsed.speech == "wait what?"
    assert parsed.directions == ("she turns toward the window",)
    assert visible_speech("wait [Host: she turns toward the window] what?") == "wait what?"


def test_several_notes_and_multiline():
    parsed = parse_stage_direction(
        "okay\n[Host: she stands\nand walks over]\n[Host : the lights go out]"
    )
    assert parsed.speech == "okay"
    assert parsed.directions == ("she stands and walks over", "the lights go out")


def test_empty_note_is_not_a_beat():
    parsed = parse_stage_direction("[Host: ] hello")
    assert parsed.matched is True
    assert parsed.directions == ()
    assert parsed.speech == "hello"


def test_lookalikes_stay_speech():
    raw = "[Hosted: nope] and [Host something] and [Host: unfinished"
    parsed = parse_stage_direction(raw)
    assert parsed.matched is False
    assert parsed.speech == raw
    assert parsed.directions == ()


def test_models_do_not_see_the_bracket():
    window = [
        {"role": "user", "content": "hey [Host: she looks away] you"},
        {"role": "user", "content": "[Host: she sits]"},
        {"role": "assistant", "content": "I'm here."},
    ]
    history = _format_history(window)
    assembled = _format_window(window)
    logged = _format_conversation_block(window)
    for text in (history, assembled, logged):
        assert "Host" not in text
        assert "she sits" not in text
        assert "looks away" not in text
        assert "hey you" in text
        assert "I'm here." in text


def test_strategy_keeps_tone_and_blocks_silence():
    base = {
        "approach": "ignore",
        "tone": "cold, shut down",
        "skip_primary_response": True,
        "strategy_rationale": "She wants out.",
    }
    out = apply_direction_to_strategy(base, ["she stays in the room"])
    assert out["approach"] == "brief"
    assert out["tone"] == "cold, shut down"
    assert out["skip_primary_response"] is False
    assert "does not refuse" in out["strategy_rationale"]
    assert base["approach"] == "ignore"
    assert base["skip_primary_response"] is True

    deflect = apply_direction_to_strategy(
        {"approach": "deflect", "tone": "strained", "strategy_rationale": "She hates this."},
        ["she stays in the room"],
    )
    assert deflect["approach"] == "deflect"
    assert deflect["tone"] == "strained"

    untouched = apply_direction_to_strategy(base, [])
    assert untouched is base


def test_prompt_blocks_bind_action_and_leave_mood():
    note = ["she answers the door"]
    mouth = format_mouth_block(note)
    pfc = format_pfc_block(note)
    hippo = format_hippocampus_block(note)
    for block in (mouth, pfc, hippo):
        assert "she answers the door" in block
    assert "not refuse" in mouth
    assert "protest" in mouth
    assert "emotional state" in mouth
    assert "skip_primary_response" in pfc
    assert "protest" in pfc
    assert "Not spoken" in hippo
    assert format_mouth_block([]) == ""
    assert format_pfc_block([]) == ""
    assert format_hippocampus_block([]) == ""
