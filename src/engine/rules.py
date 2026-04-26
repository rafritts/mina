"""
SPEC-53: Compound rules — multi-chemical state descriptions for the bio report.

Each CompoundRule fires when its condition(s, d) returns True, where:
  s = flat dict of chemical concentrations {"cortisol": 500.0, ...}
  d = derived values dict including second_order, third_order, plus:
        d["sleeping"]          bool
        d["hedonic_setpoint"]  float (from state.body)

Single-chemical threshold notes live on each ChemicalProfile.notes instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class CompoundRule:
    tag: str
    condition: Callable[[dict, dict], bool]
    description: str


COMPOUND_RULES: list[CompoundRule] = [
    CompoundRule(
        tag="stress_with_anchor",
        condition=lambda s, d: s.get("cortisol", 0) > 650 and s.get("oxytocin", 0) > 57,
        description="Acute stress held together by a strong bond. Suppression has a cost — this cannot hold indefinitely.",
    ),
    CompoundRule(
        tag="stress_no_anchor",
        condition=lambda s, d: s.get("cortisol", 0) > 650 and s.get("oxytocin", 0) < 28,
        description="Acute stress with no trust anchor. Likely to shut down or lash out.",
    ),
    CompoundRule(
        tag="cognitively_offline_sleeping",
        condition=lambda s, d: d.get("cognitive_clarity", 100) < 15 and d.get("sleeping", False),
        description="Cognitively offline — asleep. Responses must reflect this.",
    ),
    CompoundRule(
        tag="cognitively_offline_awake",
        condition=lambda s, d: d.get("cognitive_clarity", 100) < 15 and not d.get("sleeping", False),
        description="Cognitively offline while awake — severely impaired. Something is wrong.",
    ),
    CompoundRule(
        tag="hunger_amplifying_anxiety",
        condition=lambda s, d: s.get("glucose", 85) < 62 and d.get("anxiety", 0) > 60,
        description="Hunger is amplifying the anxiety. These are compounding.",
    ),
    CompoundRule(
        tag="reward_seeking_under_stress",
        condition=lambda s, d: s.get("dopamine", 0) > 200 and d.get("anxiety", 0) > 65,
        description="High reward-seeking under stress — impulsive decisions likely.",
    ),
    CompoundRule(
        tag="serotonin_floor_depression",
        condition=lambda s, d: s.get("serotonin", 22) < 14 and d.get("depression", 0) > 60,
        description="Low serotonin floor + high depression. Negative bias in all interpretation.",
    ),
    CompoundRule(
        tag="boredom_low_dopamine",
        condition=lambda s, d: d.get("boredom", 0) > 65 and s.get("dopamine", 0) < 56,
        description="Severe boredom with low dopamine — actively seeking any stimulation. Will accept poor trade-offs.",
    ),
    CompoundRule(
        tag="boredom_low_threat",
        condition=lambda s, d: d.get("boredom", 0) > 65 and s.get("cortisol", 0) < 200,
        description="Boredom distress without active threat — playfully chaotic or reckless, not fearful. Mischief-seeking.",
    ),
    CompoundRule(
        tag="boredom_depression_inertia",
        condition=lambda s, d: d.get("boredom", 0) > 65 and d.get("depression", 0) > 55,
        description="Boredom + depression: not restless chaos but heavy inertia. Wants relief but can't generate motivation. Stuck.",
    ),
    CompoundRule(
        tag="loneliness_no_bond",
        condition=lambda s, d: d.get("loneliness", 0) > 70 and s.get("oxytocin", 0) < 28,
        description="Aching loneliness with no established bond — contact-seeking urgent but trust isn't there. Approach-avoidance tension.",
    ),
    CompoundRule(
        tag="arousal_flood_impaired",
        condition=lambda s, d: s.get("norepinephrine", 0) > 1000 and d.get("cognitive_clarity", 100) < 40,
        description="Flooded with arousal but cognitively impaired — high reactivity, low judgment. Responses may be raw or unfiltered.",
    ),
    CompoundRule(
        tag="wanting_without_liking",
        condition=lambda s, d: s.get("dopamine", 0) > 180 and s.get("endorphins", 0) < 20,
        description="High wanting, low liking — seeking hard but arrival feels hollow. Addictive/obsessive pattern.",
    ),
    CompoundRule(
        tag="passive_warmth_no_drive",
        condition=lambda s, d: s.get("dopamine", 0) < 56 and s.get("endorphins", 0) > 40,
        description="Low drive, high pleasure capacity — content with what comes but won't pursue much. Passive warmth without motivation.",
    ),
    CompoundRule(
        tag="serotonin_low_loneliness_threat",
        condition=lambda s, d: s.get("serotonin", 22) < 14 and d.get("loneliness", 0) > 50,
        description="Low serotonin + loneliness: social cues are being read as threatening even when neutral. Contact may feel worse than absence.",
    ),
    CompoundRule(
        tag="serotonin_low_cortisol_high",
        condition=lambda s, d: s.get("serotonin", 22) < 14 and s.get("cortisol", 0) > 440,
        description="Low serotonin floor under active stress — impulse control is compromised. Likely to say or do something she'll regret.",
    ),
    CompoundRule(
        tag="hyperalert_underfueled",
        condition=lambda s, d: s.get("norepinephrine", 0) > 800 and s.get("glucose", 85) < 70,
        description="Hyperalert but underfueled — attention is sharp but the tank is empty. Will crash hard when the stress passes.",
    ),
    # SPEC-34: hedonic setpoint / craving rules
    CompoundRule(
        tag="setpoint_elevated_craving",
        condition=lambda s, d: d.get("hedonic_setpoint", 15) > 60 and d.get("craving", 0) > 55,
        description=(
            "Setpoint is elevated from a recent high — current state registers as severe deprivation "
            "even if chemistry looks near-normal. The want isn't for more; it's to feel normal again."
        ),
    ),
    CompoundRule(
        tag="setpoint_bonding_loss",
        condition=lambda s, d: d.get("hedonic_setpoint", 15) > 60 and s.get("oxytocin", 0) < 20 and d.get("craving", 0) > 45,
        description=(
            "The high involved bonding chemistry. The deficit isn't generic — it's attributed to a "
            "specific person. Feels like abandonment, not just emptiness."
        ),
    ),
    CompoundRule(
        tag="reward_floor_collapsed",
        condition=lambda s, d: s.get("dopamine", 0) < 56 and s.get("endorphins", 0) < 15 and d.get("craving", 0) > 60,
        description=(
            "Reward floor has collapsed. Tonic anhedonia — nothing produces a signal. The craving "
            "isn't acute wanting; it's the absence of any other feeling."
        ),
    ),
]
