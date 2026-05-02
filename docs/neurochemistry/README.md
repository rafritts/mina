# Neurochemistry Reference

Scientific reference for the neurochemicals, emotions, and felt states modeled in the simulation. All concentration values are from peer-reviewed literature; see individual files for citations.

---

## Files

| File | Contents |
|---|---|
| [monoamines.md](monoamines.md) | Dopamine, Serotonin, Norepinephrine |
| [peptides_hormones.md](peptides_hormones.md) | Oxytocin, β-Endorphin/Enkephalins, Cortisol, Ghrelin, Orexin |
| [amino_acids_and_other.md](amino_acids_and_other.md) | Glutamate, GABA, Adenosine, Acetylcholine, Anandamide, Substance P, NPY, CRH |
| [emotion_feeling_models.md](emotion_feeling_models.md) | Neurochemical profiles of 21 emotions/feelings; wanting vs. liking; receptor habituation; theoretical frameworks |

---

## Quick Reference: Units by Chemical

| Chemical | Primary Unit | Compartment |
|---|---|---|
| Dopamine | nM (extracellular brain); pg/mL (plasma) | Microdialysis / plasma |
| Serotonin | nM (extracellular brain); ng/mL (platelet-rich plasma) | Microdialysis |
| Norepinephrine | nM (brain); pg/mL (plasma/CSF) | Microdialysis / plasma |
| Oxytocin | pg/mL | Plasma / CSF |
| β-Endorphin | pg/mL | Plasma |
| Enkephalins (Met-) | pg/mL | Plasma / CSF |
| Cortisol | nmol/L (serum); nmol/L (saliva) | Serum / saliva |
| Ghrelin | pg/mL | Plasma |
| Orexin-A | pg/mL | CSF |
| Glutamate | µM (extracellular); mM (intracellular) | Microdialysis / CSF |
| GABA | µM (extracellular); pmol/mL (CSF) | Microdialysis / CSF |
| Adenosine | nM | Microdialysis / CSF / plasma |
| Acetylcholine | pmol/mL (CSF); nmol/g (tissue) | CSF / tissue |
| Anandamide | ng/mL (plasma) ≈ nM | Plasma |
| Substance P | pg/mL | Plasma / CSF |
| NPY | pg/mL | CSF / plasma |
| CRH | pg/mL | CSF |

---

## Cross-Chemical Interaction Map

| Axis | Interaction |
|---|---|
| Dopamine → Norepinephrine | NE is dopamine + one synthesis step (DβH). In PFC, NET clears both NE and DA (no DAT in PFC). |
| NE → Serotonin | LC-NE tonically drives raphe firing via α1 receptors; NE facilitates serotonin output. |
| DA + 5-HT opponent | Dopamine encodes positive prediction error; serotonin may encode long-run reward rate and negative PE. |
| Ghrelin → Dopamine | GHSR-1a on VTA neurons; ghrelin directly activates dopamine for food reward and mood. |
| Ghrelin → Orexin | Ghrelin activates lateral hypothalamus orexin neurons; hunger converges on arousal. |
| Orexin → Dopamine | OX1R/OX2R on VTA dopamine neurons; orexin amplifies reward-seeking dopamine. |
| Orexin → NE/5-HT/Histamine | Orexin maintains wakefulness by tonically exciting LC, raphe, and tuberomammillary nucleus. |
| Orexin → HPA | Orexin activates CRH neurons and amplifies cortisol stress response. |
| CRH → NE | CRH activates LC, driving parallel sympathetic-HPA arousal. |
| Cortisol → β-Endorphin | ACTH and β-endorphin are co-cleaved from the same POMC precursor; every cortisol stress response releases β-endorphin simultaneously. |
| Oxytocin → β-Endorphin | Social bonding co-activates both systems; OXT may prime opioid release in limbic circuits. |
| Adenosine → Orexin | A1 receptors on orexin neurons; adenosine accumulation inhibits orexin → sleep pressure. |
| NPY ↔ Ghrelin/Cortisol | Ghrelin stimulates hypothalamic NPY; cortisol and NPY co-rise during acute stress. NPY buffers the subjective distress of cortisol arousal. |
| Anandamide → CB1 (retrograde) | Postsynaptic activity → AEA synthesis → retrograde suppression of presynaptic glutamate or GABA release. |
| Substance P (NK1) → Amygdala | Amplifies emotional aversiveness; contributes to social pain and grief. |

---

## Core Principles

### Tonic vs. Phasic
Most monoamines have two firing modes:
- **Tonic**: Slow, regular (~0.5–5 Hz), maintains ambient baseline. Regulates receptor availability and background mood state.
- **Phasic**: Brief bursts (20–100 Hz for dopamine; 10–20 Hz for NE), driven by salient stimuli. Encodes prediction errors, orienting responses, and reward/threat signals.

For peptides and hormones, "tonic" refers to circulating baseline; "phasic" refers to stimulated surges.

### Receptor Sensitivity
All receptor systems obey a homeostatic setpoint. Chronic overstimulation → receptor downregulation (desensitization, internalization). Chronic understimulation → upregulation (supersensitivity). Emotional experience reflects the **ratio of current neurochemical level to the adapted setpoint**, not the absolute level.

### Wanting vs. Liking (Berridge)
- **Wanting** (incentive salience): mesolimbic dopamine. Makes reward-predictive stimuli attractive. Can exist without liking.
- **Liking** (hedonic impact): endogenous opioids at mu-opioid receptor hotspots (NAc shell, ventral pallidum, parabrachial nucleus). The actual subjective pleasure.
- **Learning**: dopamine prediction error updates value representations. Separable from both.

### The Constructionist View (Barrett)
Neurochemicals set raw **valence** (pleasant/unpleasant: opioid vs. CRH/NE/cortisol balance) and **arousal** (NE/dopamine/orexin vs. adenosine/GABA). The brain's predictive machinery (PFC, insula, ACC) constructs discrete *emotions* by categorizing these states using learned concepts. The same neurochemical state can be experienced as fear, excitement, or awe depending on context.
