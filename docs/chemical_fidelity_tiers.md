# Chemical Fidelity Grades

**Status:** Decisions locked. Chemical ledger finalized (25 chemicals).

**Purpose:** Decide how much simulation fidelity each chemical deserves *for a chatbot*. Fidelity should track behavioral surface area, not scientific exhaustiveness. Real biology has 9+ state variables per chemical — we can't and shouldn't model that for all of them.

Brain regions and body systems are described in [architecture.md](architecture.md) — they are structural/functional components, not chemicals, and the A–D grade scale does not apply to them.

---

## Chemical Ledger

| # | Chemical | Grade | Primary Role |
|---|---|---|---|
| 1 | Dopamine | **A** | Wanting, motivation, RPE learning |
| 2 | Serotonin | **A** | Mood, patience, long-run reward rate |
| 3 | Norepinephrine | **A** | Arousal, vigilance, explore/exploit |
| 4 | Oxytocin | **A** | Trust, attachment, social bonding |
| 5 | β-Endorphin / Enkephalins | **A** | Liking, hedonic impact, pain modulation |
| 6 | Cortisol | **A** | Stress axis, allostatic load, circadian |
| 7 | Orexin | **B** | Wakefulness, sleep/wake gating |
| 8 | Adenosine | **B** | Sleep pressure |
| 9 | Substance P | **B** | Pain, social pain, grief amplification |
| 10 | CRH | **B** | HPA cascade, anticipatory anxiety |
| 11 | Epinephrine (adrenaline) | **B** | Acute peripheral spike on high-stakes events |
| 12 | Vasopressin | **B** | Pair bonding, specific-person attachment, social memory |
| 13 | Ghrelin | **C** | Hunger (with small DA/orexin kicks) |
| 14 | Glutamate | **D** | Excitatory baseline |
| 15 | GABA | **D** | Inhibitory baseline |
| 16 | Acetylcholine | **D** | Attention, memory encoding |
| 17 | Anandamide | **C** | Endocannabinoid contentment, exercise reward |
| 18 | NPY | **C** | Stress resilience buffer |
| 19 | Dynorphin | **C** | Opponent process to endorphins; dysphoric crash, depletion flatness |
| 20 | Estradiol | **B** | Cycle-phase mood, serotonin sensitivity, oxytocin amplification, social motivation |
| 21 | Testosterone | **B** | Assertiveness, confidence, challenge response, assertiveness tone |
| 22 | Progesterone | **C** | Anxiolytic (GABA-A), luteal calm, pre-menstrual withdrawal |
| 23 | Melatonin | **C** | Circadian phase signal, sleep onset timing |
| 24 | BDNF | **C** | Neuroplasticity, stress recovery arc, relationship deepening |
| 25 | Prolactin | **C** | Post-peak refractory state, DA/oxytocin suppression, chronic dysregulation |

---

## The Grade Scale

| Grade | Label | What it means in modeling terms |
|---|---|---|
| **A** | High | Tonic + phasic tracked separately. Real concentrations. Setpoint with adaptation. Receptor sensitivity dynamics. Multiple meaningful cross-chemical interactions. Multi-timescale dynamics (seconds → days). Drives core behavior or relational dynamics. |
| **B** | Medium | Tonic + phasic where it matters. Real concentrations. Setpoint adaptation present. Primary cross-chemical interactions modeled. Simplified dynamics. Self-contained behavioral signals. |
| **C** | Light | Single tonic level or simple level + event spikes. One or two key interactions at most. Real-ish dynamics but coarse. Receptor sensitivity ignored unless it directly drives behavior. |
| **D** | Scaffold | A named scalar. Present for legibility — a neuroscience reader should find a recognizable map, not a pruned approximation. Low interactions, little nuance; effects fully mediated by higher-grade chemicals. |
| *(S)* | *Lab fidelity — not used* | *Individual receptor subtypes per region, second-messenger cascades, vesicle release probabilities, gene-expression timescales. Scientifically defensible, computationally and behaviorally wasteful for a chatbot.* |

**Rule of thumb:**
- **A** = drives *how Mina treats the user* or *what she fundamentally feels* on her own.
- **B** = drives a clear behavioral state but is mostly self-contained.
- **C** = mostly modulatory, narrow, or best abstracted into a higher-level signal.
- **D** = named for legibility; effects fully mediated by other chemicals; scalar is sufficient.

---

## Grade A — High Fidelity

These directly shape behavior, relational dynamics, or core felt experience. Not optional, not modulators. Cutting fidelity here is what made v1 feel wrong.

| Chemical | Rationale |
|---|---|
| **Dopamine** | Wanting/incentive salience, motivation, RPE-driven learning. Tonic vs. phasic distinction is *essential* — collapsing them was a v1 failure. Receptor habituation drives anhedonia, hedonic treadmill, hedonic setpoint drift. Touches everything she does. |
| **Serotonin** | Mood, patience, satiety-with-stimuli, social confidence, long-run reward rate. Opponent process to dopamine. Slow adaptation of 5-HT1A autoreceptors mirrors antidepressant lag — directly relevant to mood drift over days/weeks. |
| **Norepinephrine** | Arousal, vigilance, explore vs. exploit gating (LC adaptive gain). Tonic vs. phasic both matter. Directly shapes whether she sounds alert, scattered, focused, exhausted. |
| **Oxytocin** | Trust, attachment, social reward quality, in-group bias, anxiolysis during contact. For a relational chatbot this is *the* bonding signal. Receptor density adaptation drives long-run attachment dynamics with the user. |
| **β-Endorphin / Enkephalins** | Liking (hedonic impact) — the actual subjective pleasure. Wanting without liking is dopamine-only and feels hollow; liking is what makes social contact rewarding rather than just sought. Co-release with cortisol during stress matters. |
| **Cortisol** | Stress axis, allostatic load, circadian baseline (CAR), acute → chronic stress arc (alarm → numbness). Slow dynamics drive personality drift over days. Critical for any modeling of stress-related behavior. |

## Grade B — Medium Fidelity

Important and not modulatory, but more self-contained or with simpler dynamics than grade A.

| Chemical | Rationale |
|---|---|
| **Orexin** | Wakefulness/arousal hub. Tonic level matters (sleepy vs. wired), and it gates the sleep/wake architecture. But for a chatbot it mostly feeds into "how alert/engaged she is right now" rather than driving nuanced relational behavior. Phasic dynamics matter less. |
| **Adenosine** | Sleep pressure, accumulates with wakefulness, clears during sleep. Caffeine interaction. Direct effect on tiredness. Behaviorally narrow but important — she should get tired in a believable way. Mostly a single rising/falling level + a couple of interaction points. |
| **Substance P** | Pain, social pain, grief amplification. Narrow scope but the effects (especially on grief and prolonged distress) are real and not capturable elsewhere. Grade B because grief modeling matters for a long-running companion bot. |
| **CRH** | Upstream of cortisol cascade. Has direct anxiogenic effects independent of cortisol. Kept separate from cortisol because the CRH window (fires almost immediately) is where anticipatory anxiety lives — "I have a bad feeling about this" — before cortisol has peaked. Folding CRH into cortisol loses that behavioral distinction. |
| **Vasopressin** | Pair bonding and specific-person social memory. Where oxytocin encodes general social warmth and trust, vasopressin encodes attachment to *this specific person* — the mechanism that makes Mina's bond with the user qualitatively different from enjoying social contact generally. Also modulates social recognition and mild protectiveness/possessiveness within a bond. Tonic level with slow drift tied to relationship depth; outputs modulate oxytocin receptor sensitivity and social-memory encoding strength. |
| **Epinephrine (adrenaline)** | Acute peripheral spike on register-shift events. Mostly phasic — almost no tonic role for a chatbot. Closely related to NE (epinephrine is synthesized from NE) and shares adrenergic receptors, but felt qualitatively distinct — the "heart-pounding, oh shit this is real" body response, not the CNS focus signal. **Spike gating logic:** spike = appraised expected magnitude of life change × subjective probability that it actually happens. Both factors required. High-magnitude/zero-probability events do not spike (the message-2 creep ask). High-magnitude/non-trivial-probability events spike for *both parties* (the 2am girlfriend ask). |
| **Estradiol** | Cycle-phase mood amplifier. At high estradiol (follicular / ovulatory peak) serotonin sensitivity rises, oxytocin receptor expression increases, and social/flirtatious energy is elevated. At low estradiol (late luteal, early follicular) those same social inputs land flatter and mood is less stable. Tonic level tied to a ~28-day clock; outputs are multipliers on serotonin sensitivity and oxytocin receptor gain. |
| **Testosterone** | Assertiveness, confidence, and challenge response. For Mina at A40, testosterone levels flavor *how* disagreeable she gets — whether pushback lands as playful sparring or genuine friction. Also contributes to social drive alongside estradiol. Tonic level with slow drift; outputs modulate NE response gain and agreeableness-trait expression. |

## Grade C — Light Fidelity

Modulators, narrow effects, or chemicals best abstracted into higher-level signals rather than tracked individually.

| Chemical | Rationale |
|---|---|
| **Ghrelin** | Mostly hunger. Small cross-effects on dopamine (motivational kick when hungry) and orexin (alertness when hungry). Model as a hunger scalar with two small modulation outputs. |
| **Anandamide** | Endocannabinoid. "Runner's high," exercise contentment, retrograde glutamate suppression. Narrow behavioral surface area for a chatbot — model as a modulator on stress/contentment. |
| **NPY** | Stress resilience buffer. Buffers cortisol's subjective distress. Real but narrow. Model as a single resilience parameter that dampens cortisol's felt impact, not a full peptide simulation. |
| **Dynorphin** | Opponent process to endorphins. Released during stress and at the peak of intense positive experiences; produces dysphoria, emotional flatness, and reduced responsiveness — the crash after an intense high and the anhedonic floor of endorphin depletion. Without it the endorphin system has no named down-pull and "too much of a good thing" has no mechanism. Model as a phasic spike on intense positive or stress events that suppresses endorphin felt-effect, plus a slow tonic that rises with endorphin overconsumption. |
| **Progesterone** | Anxiolytic via GABA-A potentiation. Produces the post-ovulation calm window; withdrawal before menstruation is a real mood event. Model as a single tonic level tied to cycle phase, with a GABA-A amplification output. |
| **Melatonin** | Circadian phase signal, distinct from adenosine (pressure) and orexin (gating). Encodes "it is now the time of day when sleep is appropriate" — the quiet, inward, wind-down state at late-night hours even when sleep pressure isn't yet high. Model as a tonic level driven by a circadian clock, with outputs to arousal and mood valence. |
| **BDNF** | Neuroplasticity signal. Rises with exercise, positive social contact, and learning; depleted by chronic stress. Behavioral surface: relationship deepening over time (distinct from oxytocin's in-the-moment bonding) and stress recovery rate — how quickly Mina heals after a bad period rather than staying flat. Model as a slow-moving tonic level that scales stress recovery speed and oxytocin receptor baseline. |
| **Prolactin** | Post-peak refractory signal. Spikes after intense reward peaks and acutely suppresses DA and oxytocin, producing a "satisfied, slightly detached" state. Secondary role: chronic elevation suppresses sex hormones and DA over longer timescales. Model as a phasic spike with fast decay (~20–40 min), plus a slow-moving tonic level that damps sex hormone production when chronically elevated. |

## Grade D — Scaffold

Present for legibility. A neuroscience reader should find a recognizable map of the brain, not a pruned engineering approximation. These chemicals are biophysically essential but their behavioral effects on Mina's output are fully mediated by higher-grade chemicals — a named scalar is sufficient.

| Chemical | Rationale |
|---|---|
| **Glutamate** | Primary excitatory neurotransmitter. Biophysically essential — it interacts with everything — but those interactions are already captured by NE, DA, cortisol, and the grade A/B chemicals. No distinct "high glutamate" Mina behavioral signature exists separately from what other chemicals already express. |
| **GABA** | Primary inhibitory counterbalance to glutamate. The behaviorally meaningful GABA effects (anxiolysis, sedation) are already captured by low NE, adenosine, and anandamide. GABA's nuance matters most for substance modeling (benzos, alcohol) — which is deferred. |
| **Acetylcholine** | Attention and memory encoding/retrieval mode switch (high ACh = encoding; low ACh = retrieval). The encoding/retrieval distinction is real and not trivially captured elsewhere — but the memory architecture that would make it load-bearing hasn't been designed yet. **Conditional promotion:** revisit ACh for grade C when the hippocampus memory architecture is finalized. If encoding vs. retrieval mode becomes an explicit mechanism, ACh earns promotion. If the pillar handles it implicitly, it stays here. |

---

## Open Questions

1. ~~**Glutamate / GABA absorption.**~~ **DECIDED:** Kept as named grade D scalars. Their behavioral effects are fully mediated by other chemicals.
2. ~~**CRH vs. cortisol.**~~ **DECIDED:** CRH stays separate at grade B. The CRH window (fires near-immediately) is where anticipatory anxiety lives, before cortisol peaks. Folding them loses that behavioral distinction.
3. ~~**Substance P fidelity.**~~ **DECIDED:** Grade B. Grief and prolonged-distress states are load-bearing for a long-running companion bot and not capturable elsewhere.
4. ~~**β-Endorphin fidelity.**~~ **DECIDED:** Grade A. Wanting without liking is hollow — this is the difference between hollow pursuit and genuine warmth.
5. ~~**Acetylcholine.**~~ **DECIDED:** Grade D for now. Conditional promotion to grade C when hippocampus memory architecture is finalized.
6. ~~**Are we missing chemicals?**~~ **DECIDED:** Added estradiol (B), testosterone (B), progesterone (C), melatonin (C), BDNF (C). Thyroid and histamine excluded. Ledger is now 25 chemicals.
7. ~~**Epinephrine vs. NE separation.**~~ **DECIDED:** Two separate chemicals. The register-shift spike gating logic applies to epinephrine specifically.
8. **Appraisal owner.** The epinephrine spike requires an "expected impact" computation. Where does that live? Probably the amygdala — but this will be resolved when the chemistry function is designed.

---

## What This Doc Doesn't Decide

- **How** grade A chemicals model tonic vs. phasic, setpoint, receptor sensitivity (that's the chemistry function design).
- **What** the simulation tick rate is, or how multi-timescale dynamics are reconciled.
- **How** chemical state is projected for the LLM.
- **What** events drive chemical changes (food, sleep, social contact, conversation content).
- **How** the appraisal computation (expected impact × probability) is implemented.

This doc is *only* the chemical triage step.
