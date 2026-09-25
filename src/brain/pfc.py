"""
PFC — reasoning / integration pillar.

Synthesizes emotional state (insula), situational context (hippocampus), and
the current message into an executive response strategy. Also constructs the
system prompt that Mina receives.

Big 5 injected: neuroticism and conscientiousness modulate how much of the
felt state shows in Mina's response (Principle 6 backend regulation).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import MODEL, IDENTITY_DIR

_SYSTEM = """\
You are the prefrontal cortex — Mina's executive reasoning and integration center.

You receive:
  - Her current emotional state (insula output)
  - Situational context (hippocampus output)
  - The current message
  - Her Big 5 personality vector

Your job:
  1. Decide how she should respond (approach, tone, strategy)
  2. Determine how much of her felt state to express vs. contain (backend regulation)

## Backend regulation principle

Chemistry has already been committed — she feels what she feels. This is about \
*expression*, not experience. High conscientiousness → more containment, more composure. \
High neuroticism → the felt state leaks through more, harder to hold together. \
Neither is better — both are authentic. Do not suppress authentic affect; modulate its expression.

## Output schema (JSON, nothing else)

{
  "internal_reaction":    "raw first-person thought, her voice, unpolished",
  "approach":             "banter | sincere | question | deflect | ignore | vulnerable | warm | brief",
  "tone":                 "one-line descriptor",
  "lead_with":            "what to open with",
  "subtext_detected":     null or "the unstated thing",
  "lean_into_subtext":    true|false,
  "strategy_rationale":   "why this approach",
  "skip_primary_response":false
}

skip_primary_response should be true only if choosing complete silence is the \
right response — rare.
"""

_MINA_SYSTEM_TEMPLATE = """\
{identity}

{customization}

[Emotional State]
{emotional_state}

[Situational Context]
{situational_context}
{live_scene_section}
[Response Strategy]
{response_strategy}
"""


def run_pfc(
    insula_output: dict,
    context_output: dict,
    message: str,
    big5: dict[str, float],
    scene_block: str = "",
    *,
    stage_directions: list[str] | None = None,
) -> dict:
    """Run the PFC reasoning pillar. Returns strategy dict."""
    emotional_block    = _format_emotional(insula_output)
    context_block      = _format_context(context_output)
    big5_block         = _format_big5(big5)

    from src.brain.time_context import format_host_time_line

    scene_section = ""
    if scene_block and scene_block.strip():
        scene_section = (
            f"## Live scene (prior snapshot)\n{scene_block.strip()}\n\n"
        )

    from src.brain.stage_direction import format_pfc_block

    direction_block = format_pfc_block(stage_directions or [])
    direction_section = f"{direction_block}\n\n" if direction_block else ""

    user_prompt = (
        f"## Wall clock\n{format_host_time_line()}\n\n"
        f"## Current message\n{message}\n\n"
        f"{direction_section}"
        f"## Emotional state\n{emotional_block}\n\n"
        f"## Situational context\n{context_block}\n\n"
        f"{scene_section}"
        f"{big5_block}"
    )

    try:
        resp = chat_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        raw = resp.choices[0].message.content or ""
        result = _parse_strategy(raw)
        log("PFC", f"approach={result.get('approach','')} skip={result.get('skip_primary_response',False)}")
        return result
    except Exception as e:
        log("PFC/ERR", str(e))
        return _default_strategy()


def build_system_prompt(
    insula_output: dict,
    context_output: dict,
    pfc_output: dict,
    scene_block: str = "",
) -> str:
    """Construct Mina's system prompt from pillar outputs."""
    identity      = _load_identity()
    customization = _load_customization()

    emotional_block = "\n".join(f"{k}: {v}" for k, v in insula_output.items())
    context_block   = "\n".join(f"{k}: {v}" for k, v in context_output.items())
    strategy_block  = "\n".join(
        f"{k}: {v}" for k, v in pfc_output.items()
        if k != "internal_reaction"  # internal_reaction is for her eyes only (already in strategy)
    )
    # internal_reaction is included — it grounds her voice
    if "internal_reaction" in pfc_output:
        strategy_block = f"internal_reaction: {pfc_output['internal_reaction']}\n" + strategy_block

    live_scene_section = ""
    if scene_block and scene_block.strip():
        live_scene_section = f"\n{scene_block.strip()}\n\n"
    else:
        live_scene_section = "\n"

    return _MINA_SYSTEM_TEMPLATE.format(
        identity=identity.strip(),
        customization=customization.strip(),
        emotional_state=emotional_block,
        situational_context=context_block,
        live_scene_section=live_scene_section,
        response_strategy=strategy_block,
    ).strip()


def _load_identity() -> str:
    path = os.path.join(IDENTITY_DIR, "MINA.md")
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return "You are Mina."


def _load_customization() -> str:
    from src.config.config import REPO_ROOT
    path = os.path.join(REPO_ROOT, "CUSTOMIZATION.md")
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return ""


def _format_emotional(insula: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in insula.items())


def _format_context(context: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in context.items())


def _format_big5(big5: dict[str, float]) -> str:
    parts = [f"{k}={v:.0f}" for k, v in big5.items()]
    return f"## Big 5\n{', '.join(parts)}\n"


def _parse_strategy(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        d = json.loads(raw)
        valid_approaches = {"banter","sincere","question","deflect","ignore","vulnerable","warm","brief"}
        approach = str(d.get("approach", "sincere")).lower()
        if approach not in valid_approaches:
            approach = "sincere"
        return {
            "internal_reaction":    str(d.get("internal_reaction", "")),
            "approach":             approach,
            "tone":                 str(d.get("tone", "")),
            "lead_with":            str(d.get("lead_with", "")),
            "subtext_detected":     d.get("subtext_detected"),
            "lean_into_subtext":    bool(d.get("lean_into_subtext", False)),
            "strategy_rationale":   str(d.get("strategy_rationale", "")),
            "skip_primary_response":bool(d.get("skip_primary_response", False)),
        }
    except (json.JSONDecodeError, Exception):
        return _default_strategy()


def _default_strategy() -> dict:
    return {
        "internal_reaction": "",
        "approach": "sincere",
        "tone": "warm, present",
        "lead_with": "genuine engagement",
        "subtext_detected": None,
        "lean_into_subtext": False,
        "strategy_rationale": "Default to open, warm engagement.",
        "skip_primary_response": False,
    }
