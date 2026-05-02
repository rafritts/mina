# Monoamines: Dopamine, Serotonin, Norepinephrine

Catecholamine and indoleamine neurotransmitters. All share VMAT2 vesicular packaging, monoamine oxidase (MAO) degradation, and tonic/phasic dual-firing modes with autoreceptor negative feedback.

---

## DOPAMINE (DA)

### Class and Type
Catecholamine monoamine neurotransmitter, neuromodulator, and neurohormone (tuberoinfundibular pathway). Precursor in the synthesis chain: tyrosine → L-DOPA → **dopamine** → norepinephrine → epinephrine.

### Where Synthesized
Neurons expressing tyrosine hydroxylase (TH), the rate-limiting enzyme:
- **Ventral Tegmental Area (VTA)**: origin of mesolimbic (→ NAc, amygdala) and mesocortical (→ PFC) pathways. ~55–65% of VTA neurons are TH+.
- **Substantia Nigra pars compacta (SNc)**: densest TH expression in brain; origin of nigrostriatal pathway (→ dorsal striatum). The target of Parkinson's disease.
- **Arcuate/periventricular hypothalamus**: tuberoinfundibular pathway; tonically inhibits prolactin secretion.
- **Olfactory bulb, retina, zona incerta**: minor sources.

Synthesis (two enzymatic steps):
1. Tyrosine + O₂ + tetrahydrobiopterin → **L-DOPA** (tyrosine hydroxylase; rate-limiting; vitamin B6-dependent)
2. L-DOPA → **Dopamine** (aromatic L-amino acid decarboxylase / AADC)

### Where Stored
- Packaged into dense-core synaptic vesicles by **VMAT2** (vesicular monoamine transporter 2).
- Concentrated at axon terminals and dendritic varicosities.
- Cytoplasmic pool also exists but is rapidly degraded by MAO; VMAT2 packaging is protective.
- Somatodendritic release also occurs (important for autoreceptor feedback).

### Release Dynamics

**Tonic (baseline)**:
- 0.2–10 Hz, single spikes, intrinsically generated pacemaker activity.
- Produces low, steady extracellular dopamine via volume transmission.
- Sets ambient dopamine "tone" that occupies D2-class autoreceptors.
- Maintained partly by low-rate DAT reversal.

**Phasic (burst)**:
- 20–100 Hz bursts lasting <200 ms, driven by glutamatergic (NMDA) input from cortex, striatum, limbic regions.
- Each burst releases large vesicular dopamine into the synaptic cleft.
- Rapid reuptake by DAT; signal clears within seconds.
- Encodes **Reward Prediction Error (RPE)**:
  - Better-than-expected outcome → phasic burst (positive RPE)
  - Expected outcome → no change
  - Worse-than-expected / omission → phasic pause below baseline (negative RPE)
- The pause state (dopamine neurons silent ~0 Hz) signals negative prediction error when expected reward fails to arrive.

### Units of Measurement
| Context | Unit |
|---|---|
| Extracellular brain (microdialysis) | nM (nanomolar) |
| Synaptic cleft peak (modeled/FSCV) | µM to low mM |
| Tissue content | fmol/mg or pg/mg tissue |
| Plasma | pg/mL |
| CSF | pg/mL or pmol/mL |

### Real-Life Concentration Ranges

**Tonic / resting (extracellular brain, microdialysis)**:
| Region | Concentration |
|---|---|
| Striatum (zero-net-flux) | ~7–20 nM; dark cycle ~14.7 nM, light cycle ~9.3 nM |
| Nucleus accumbens | ~4.2 ± 0.2 nM |
| Prefrontal cortex | ~0.1–1 nM (low innervation density) |
| Plasma (resting human) | ~20–100 pg/mL (~0.13–0.65 nM; mostly peripheral) |

*Note: microdialysis underestimates true extracellular concentrations due to probe recovery; corrected striatal tonic DA may be ~40–50 nM.*

**Phasic peaks**:
| Measurement | Concentration |
|---|---|
| Synaptic cleft (modeled, FSCV + computation) | ~hundreds µM to ~1.6 mM (NAc phasic events) |
| Extrasynaptic phasic transients (FSCV) | ~0.5–2 µM near release sites |
| After DAT reuptake | Returns to baseline within <2 seconds |
| Cocaine/amphetamine-evoked | Exaggerated, persists minutes (DAT blocked) |

### Receptors
All GPCRs. Two families:

**D1-like (Gs-coupled → ↑cAMP)**:
| Receptor | Location | Notes |
|---|---|---|
| D1 | Striatum, NAc core, olfactory bulb, frontal cortex, SNc | Lower affinity; requires µM DA; most abundant DA receptor |
| D5 | Hippocampus, hypothalamus, thalamus | Higher affinity for DA than D1 |

**D2-like (Gi-coupled → ↓cAMP)**:
| Receptor | Location | Notes |
|---|---|---|
| D2 | Striatum, NAc, VTA somatodendritic autoreceptors, pituitary | ~10–100× higher affinity than D1; activated by tonic DA; primary antipsychotic target |
| D3 | NAc shell, olfactory tubercle, limbic regions | Highest DA affinity of all subtypes; sensitive to low ambient DA |
| D4 | Frontal cortex, amygdala, midbrain | Intermediate affinity; low basal ganglia expression |

**Functional roles**:
- D1 in striatum: direct pathway (go signal), LTP-like plasticity
- D2 in striatum: indirect pathway (no-go signal), LTD-like plasticity
- D2 somatodendritic autoreceptors (VTA/SNc): reduce firing rate (negative feedback)
- D2 presynaptic terminal autoreceptors: reduce vesicle release

### Receptor Sensitivity and Habituation
- **D2 autoreceptors**: prolonged DA exposure causes time-dependent decrease in autoinhibitory response via PKC and concurrent D1/D2 co-stimulation.
- **Chronic drug exposure** (cocaine, amphetamine, alcohol, nicotine): consistent D2 downregulation (measured by PET). Key substrate of addiction — decreased D2 → reward deficit → compulsive use.
- **D2S autoreceptors** (short splice form): calcium-dependent desensitization. D2L (long form) does not desensitize similarly.
- **Behavioral sensitization**: alters D1:D2 ratio; escalating drug responses.
- D3 receptors: relatively resistant to agonist-induced desensitization vs. D2.

### CNS vs. Peripheral
Predominantly **CNS** for behavioral functions. Peripheral dopamine exists (adrenal medulla, gut, kidney) as vasoactive/paracrine signal but does **not** cross the BBB.

### Reuptake and Degradation
**Primary clearance**: reuptake via **DAT** (dopamine transporter, SLC6A3). Co-transports 2 Na⁺, 1 Cl⁻, 1 DA. Target of cocaine (competitive blocker) and amphetamine (reverse transport).

**Enzymatic degradation**:
1. **MAO-A/B** (intracellular, mitochondria): oxidative deamination → DOPAC
2. **COMT** (catechol-O-methyltransferase, extracellular/cytoplasmic): methylation → 3-MT
3. Sequential → **HVA** (homovanillic acid): major urinary metabolite

**Regional notes**:
- **PFC**: COMT dominates (low DAT density); COMT Val158Met polymorphism affects PFC function and working memory.
- **Striatum**: DAT dominates.
- COMT inhibition increases DA signals ~2× in some regions.

### Half-Life
| Compartment | Half-Life |
|---|---|
| Synaptic cleft | Milliseconds to <2 seconds (DAT clearance) |
| Extracellular volume | Seconds to ~1–2 min (diffusion + DAT + COMT) |
| Plasma | ~1–5 min (mean ~2 min; MAO + COMT in liver/kidney) |

### Key Brain Regions
- VTA (synthesis, reward circuit origin)
- Nucleus accumbens (reward, motivation, addiction)
- Prefrontal cortex (working memory, executive function)
- Dorsal striatum / caudate / putamen (motor learning, habits)
- Amygdala (emotional salience tagging)
- Hippocampus (contextual memory; D1/D5)
- Substantia nigra (motor control; Parkinson's)

### Primary Effects on Mood and Behavior
- Reward anticipation ("wanting," not "liking")
- Reinforcement learning via RPE signals
- Working memory (inverted-U: too little or too much impairs)
- Motor initiation and fluidity
- Executive function, attention, impulse control
- Prolactin suppression (tuberoinfundibular)

### High DA Phenotype
Intense motivation and wanting (not necessarily pleasure); racing goal-directed thought; impulsivity; risk-taking; aggression; disrupted sleep. At extremes: grandiosity, mania, psychosis (positive symptoms of schizophrenia linked to hyperdopaminergia in mesolimbic pathway).

### Low DA Phenotype
Anhedonia; apathy; fatigue; concentration difficulty; psychomotor slowing; loss of drive; tremor/rigidity if nigrostriatal (Parkinson's); negative symptoms of schizophrenia (flat affect, social withdrawal); depression with prominent motivational deficit.

---

## SEROTONIN (5-Hydroxytryptamine / 5-HT)

### Class and Type
Indoleamine monoamine neurotransmitter and hormone. Derived from tryptophan. Functions as a CNS neurotransmitter and as a peripheral signaling molecule in the GI tract, cardiovascular system, and platelets.

### Where Synthesized
**CNS (~2% of total body serotonin)**:
- Almost entirely in the **raphe nuclei** (9 nuclei, B1–B9) along the brainstem midline.
- **Dorsal raphe nucleus (DRN)**: largest serotonergic nucleus; projects to forebrain (cortex, limbic system, striatum, thalamus).
- **Median raphe nucleus (MRN)**: projects to hippocampus, septum, hypothalamus; more involved in spatial memory.
- Caudal raphe (B1–B3): project to spinal cord, brainstem; regulate pain, autonomic function.

**Peripheral (~98% of total body serotonin)**:
- **Enterochromaffin (EC) cells of the GI tract**: ~90% of body serotonin; regulates gut motility.
- **Platelets**: do not synthesize but avidly take up plasma 5-HT via SERT; stored in dense granules (~8% of body pool).
- **Pineal gland**: serotonin is precursor to melatonin (serotonin → N-acetylserotonin → melatonin via AANAT and HIOMT).

Synthesis (two steps):
1. L-Tryptophan → **5-Hydroxytryptophan (5-HTP)** (tryptophan hydroxylase, rate-limiting; requires Fe²⁺ and BH4)
   - **TPH1**: gut/pineal (peripheral isoform)
   - **TPH2**: raphe nuclei (CNS isoform; clinically more relevant)
2. 5-HTP → **Serotonin** (AADC; same enzyme as dopamine synthesis)

Brain serotonin synthesis is sensitive to dietary tryptophan availability (unlike dopamine, where tyrosine is rarely rate-limiting).

### Where Stored
- CNS: synaptic vesicles via **VMAT2** in raphe neurons.
- Gut EC cells: dense-core vesicles; released into gut lumen and portal blood.
- Platelets: dense granules (δ-granules); released during platelet activation at vascular injury.
- Does **not** cross the BBB — peripheral and central pools are entirely independent.

### Release Dynamics

**Tonic (raphe neurons)**:
- Highly regular "clocklike" firing: **0.5–3 Hz** during wakefulness.
- Produces steady baseline 5-HT at projection targets.
- **State-dependent**: highest during active wakefulness → ~50% of waking rate during NREM sleep → near-silent during REM sleep (~38% of waking in cat DRN).
- Regulated by: somatodendritic 5-HT1A autoreceptors (negative feedback), NE input from LC (facilitates via α1), GABA interneurons (tonic inhibition).

**Phasic responses**:
- Glutamate (AMPA/NMDA) drives phasic excitatory bursts in raphe neurons.
- DRN neurons show heterogeneous phasic responses:
  - Many fire phasically to reward-predictive cues AND punishment.
  - A subset preferentially encodes punishment.
  - Theoretical role: tonic 5-HT may encode long-run average reward; phasic may encode punishment prediction error (opponent to dopamine's reward PE).

**GI release**: EC cells release 5-HT in response to mechanical pressure/distension → activates intrinsic sensory neurons (5-HT3 and 5-HT4) → drives peristalsis.

### Units of Measurement
| Context | Unit |
|---|---|
| Brain extracellular (microdialysis) | nM or fmol per µL perfusate |
| Tissue content | fmol/mg or ng/mg tissue |
| Plasma (total, platelet-rich) | ng/mL |
| Free plasma 5-HT | nM (very low; rapidly absorbed by platelets) |
| Urine metabolite 5-HIAA | µmol/24h or mg/24h |

### Real-Life Concentration Ranges

**Tonic / resting (extracellular brain, microdialysis)**:
| Region | Concentration |
|---|---|
| Dorsal raphe nucleus | ~5–10 nM; ~4.02 fmol/5µL perfusate (awake cat) |
| Prefrontal/frontal cortex | ~0.18–5 nM (strict basal ~0.2–0.5 nM) |
| Striatum | ~68.4 nM (high SERT density; highest reported region) |
| Hippocampus | ~1–3 nM |
| Hypothalamus | ~1–4 nM |
| Plasma (platelet-rich, total) | ~0.5–1.0 µg/mL (2.8–5.7 µM); reflects platelet storage |
| Free plasma 5-HT (platelet-poor) | ~1–3 nM (extremely low; SERT on platelets clears free 5-HT) |

**Phasic peaks**:
- Following raphe electrical stimulation: extracellular 5-HT rises and declines with half-life ~1 second (baseline); ~2 seconds with SSRI.
- Synaptic cleft peak during burst firing: likely **low-to-mid µM range** (0.1–10 µM) — poorly characterized due to rapid SERT clearance.
- SSRI administration: increases extracellular 5-HT **3–6×** in raphe and forebrain.
- Acute tryptophan depletion: decreases brain 5-HT by ~50–80%.

### Receptors
14 subtypes across 7 families. All GPCRs except 5-HT3 (ion channel).

**5-HT1 family (Gi/Go → ↓cAMP; inhibitory)**:
| Receptor | Location | Key Role |
|---|---|---|
| **5-HT1A** | Raphe (somatodendritic autoreceptors), hippocampus (CA1, DG), frontal cortex, septum, amygdala | Anxiolytic; autoreceptor negative feedback; key SSRI target |
| 5-HT1B | Terminal autoreceptors throughout; globus pallidus, trigeminal | Regulates 5-HT release; triptan target (migraine) |
| 5-HT1D | Cerebral blood vessels, trigeminal system | Migraine |
| 5-HT1E/F | Cortex, hippocampus (1E); neocortex (1F) | Poorly characterized; migraine |

**5-HT2 family (Gq → ↑IP3/DAG; excitatory)**:
| Receptor | Location | Key Role |
|---|---|---|
| **5-HT2A** | Frontal cortex (layer V pyramids), neocortex, claustrum, NAc, basal ganglia | Wakefulness, perception; psychedelic target (LSD, psilocybin); antipsychotic target (antagonists) |
| 5-HT2B | Stomach fundus, heart, cerebellum | Cardiovascular; cardiac valvulopathy risk |
| **5-HT2C** | Choroid plexus (dense), amygdala, hippocampus, striatum | Appetite suppression; mood; modulates mesolimbic dopamine |

**5-HT3 (ionotropic — Na⁺/K⁺/Ca²⁺ cation channel; fast excitatory)**:
- Amygdala, hippocampus, entorhinal cortex, area postrema (vomiting center), gut.
- Antiemetic target (ondansetron).

**5-HT4 (Gs → ↑cAMP)**:
- Striatum, hippocampus, cortex, entire enteric NS. Enhances ACh release; promotes peristalsis; learning/memory.

**5-HT5A (Gi/Go)**:
- Hippocampus, cortex, cerebellum; locomotion/memory modulation.

**5-HT6 (Gs → ↑cAMP)**:
- Striatum, NAc, olfactory tubercle, hippocampus, cortex. Regulates glutamate and ACh release; cognition enhancement target.

**5-HT7 (Gs → ↑cAMP)**:
- Hippocampus, thalamus, hypothalamus, cortex, limbic system. Circadian rhythm (SCN), thermoregulation, REM sleep modulation.

### Receptor Sensitivity and Habituation
- **5-HT1A autoreceptors (raphe)**: Chronic SSRI → desensitization (~18% reduction by PET). This desensitization, taking 2–4 weeks, is theorized to be *necessary* for antidepressant effect. Before desensitization, increased synaptic 5-HT activates autoreceptors and reduces firing, blunting net output. After desensitization, the autoinhibitory brake lifts and net serotonin transmission rises.
- High autoreceptor levels in raphe = vulnerability to stress and poor SSRI response.
- **5-HT2A receptors**: downregulate with chronic agonist (psychedelic) exposure; also downregulated by chronic antidepressants.
- **5-HT3**: rapid desensitization within seconds of sustained activation (typical for ligand-gated channels).

### CNS vs. Peripheral
**Strongly dual**: ~98% of body serotonin is peripheral. CNS and peripheral pools are functionally independent (5-HT does not cross BBB). Peripheral 5-HT regulates GI motility, platelet aggregation, vasoconstriction/dilation, fetal development, liver regeneration, bone metabolism.

### Reuptake and Degradation
**Primary clearance**: **SERT** (serotonin transporter, SLC6A4) — the target of SSRIs. Also present on platelets (primary sequestration mechanism). Secondary low-affinity uptake by **PMAT** when SERT is saturated.

**Enzymatic degradation**:
- **MAO-A** (preferential; MAO-B minor): 5-HT → 5-HIAL →
  - Aldehyde dehydrogenase → **5-HIAA** (major urinary metabolite)
  - Aldehyde reductase → 5-hydroxytryptophol (minor)
- Pineal: 5-HT → N-acetylserotonin → **melatonin** (AANAT + HIOMT)

### Half-Life
| Compartment | Half-Life |
|---|---|
| Synaptic cleft | ~1 second (2 sec with SSRI) |
| Free plasma | Seconds to minutes (platelet SERT clears rapidly) |
| Platelet-bound 5-HT | 3+ days (parallels platelet lifespan ~7–10 days) |
| Newly released circulating 5-HT | t½ ~2.5 days (platelet turnover dynamics) |

### Key Brain Regions
- Dorsal raphe nucleus (synthesis, autonomic integration)
- Median raphe nucleus (hippocampal modulation)
- Prefrontal cortex (emotional regulation, top-down control)
- Amygdala (fear/anxiety modulation via 5-HT1A/2A)
- Hippocampus (neurogenesis, memory; dense 5-HT1A)
- Nucleus accumbens (reward modulation, dopamine interaction)
- Hypothalamus (appetite, thermoregulation, circadian)
- Thalamus / SCN (sleep-wake, circadian; 5-HT7)
- Spinal cord dorsal horn (descending pain gating)
- GI tract / enteric NS (~90% of body 5-HT)

### Primary Effects on Mood and Behavior
- Mood stability and emotional regulation (tonic 5-HT → equanimity)
- Anxiety/fear modulation (5-HT1A anxiolytic; 5-HT2A anxiogenic at high levels)
- Sleep: promotes slow-wave sleep; 5-HT2A and 5-HT7 modulate REM
- Appetite and satiety: 5-HT2C reduces appetite
- Cognition: 5-HT6 and 5-HT4 support working memory and ACh modulation
- Social behavior: affiliative behavior, social dominance hierarchy maintenance
- Pain modulation: descending serotonergic projections suppress dorsal horn pain
- GI motility (enteric NS)

### High 5-HT Phenotype
Calm, emotionally stable, socially confident, affiliative. At extreme (serotonin syndrome — drug-induced): hyperthermia, myoclonus, hyperreflexia, agitation, diaphoresis, tachycardia — potentially fatal. Psychedelic states (5-HT2A over-activation): perceptual distortions, ego dissolution, time distortion.

### Low 5-HT Phenotype
Depressed mood, emotional lability, irritability, anxiety, impaired impulse control, sleep disturbance (especially early-morning waking), increased pain sensitivity, appetite dysregulation (carbohydrate craving). *Caveat: direct causation between low serotonin and depression is contested (Moncrieff et al., 2022); the picture is substantially more complex.*

---

## NOREPINEPHRINE (Noradrenaline / NE / NA)

### Class and Type
Catecholamine monoamine neurotransmitter, neuromodulator, and stress hormone. Structurally: dopamine + a hydroxyl group on the beta carbon (added by dopamine β-hydroxylase). Functions as both:
- A **CNS neurotransmitter** (locus coeruleus system)
- A **peripheral hormone/transmitter** (adrenal medulla; sympathetic postganglionic neurons)

### Where Synthesized
**CNS**:
- **Locus coeruleus (LC)**: small bilateral nucleus in the pontine tegmentum; ~15,000 neurons per side in humans. Despite its size, supplies **~70% of all CNS norepinephrine** and projects to virtually every brain region.
- Other NE nuclei (A1–A7 cell groups): lateral tegmental field, medullary noradrenergic neurons — project to brainstem, spinal cord, hypothalamus.

**Peripheral**:
- **Adrenal medulla**: chromaffin cells produce ~20% NE and ~80% epinephrine; released into bloodstream.
- **Sympathetic postganglionic neurons**: NE is the primary transmitter at effector organs (except sweat glands which use ACh).

Synthesis (NE is one step beyond dopamine):
1. Tyrosine → L-DOPA (tyrosine hydroxylase, rate-limiting)
2. L-DOPA → Dopamine (AADC)
3. **Dopamine → Norepinephrine** (dopamine β-hydroxylase, **DβH**; inside synaptic vesicles; requires copper and ascorbate)

*DβH is located inside the vesicle lumen — conversion from DA to NE occurs within the vesicle itself. LC neurons have no significant cytoplasmic NE pool.*

### Where Stored
- Exclusively in **large dense-core vesicles (LDCV)** and smaller clear-cored vesicles at axon terminals.
- Rapidly recycled back into vesicles after reuptake via VMAT2.
- Adrenal medulla: large chromaffin granules co-containing NE, epinephrine, ATP, chromogranins, and NPY.

### Release Dynamics (Aston-Jones & Cohen Adaptive Gain Model)

**Tonic mode (baseline arousal)**:
- **0.5–3 Hz** irregular spontaneous firing during wakefulness; lower during NREM; near-silent during REM (concurrent with 5-HT raphe silence).
- Sets baseline **arousal** and neural signal-to-noise ratio ("gain") across all target regions.
- Too low tonic NE → drowsiness, poor alertness.
- Optimal moderate tonic NE → focused attentiveness.
- High chronic tonic NE → anxious, distractible, impaired performance (noise amplification).

**Phasic mode (salient stimuli)**:
- **10–20 Hz** bursts lasting ~200–500 ms.
- Triggered by: (a) unexpected/intense/behaviorally relevant stimuli; (b) decision-completion signals from ACC and OFC.
- Followed by post-burst autoinhibition (300–700 ms via α2 somatodendritic autoreceptors).
- Phasic NE sharpens behavioral responding; promotes **exploitation** (staying on current task).
- When task utility declines, tonic mode elevates → promotes **exploration** (disengagement, sampling alternatives).

### Units of Measurement
| Context | Unit |
|---|---|
| Brain extracellular (microdialysis) | nM |
| Tissue content | pg/mg or fmol/mg tissue |
| CSF | pg/mL (~6 nM per 1000 pg/mL; MW 169 g/mol) |
| Plasma | pg/mL |
| Urine metabolite MHPG | µg/24h (brain-derived NE metabolite) |

### Real-Life Concentration Ranges

**Tonic / resting**:
| Compartment | Concentration |
|---|---|
| Rodent hippocampus (microdialysis, corrected) | ~14–35 nM |
| Rodent cortex | ~10–30 nM |
| CSF (young healthy adults) | ~154 pg/mL (SD 53); older: ~219 pg/mL (SD 88) |
| CSF range | ~100–200 pg/mL (~0.6–1.2 nM) |
| Plasma (supine, resting) | ~100–250 pg/mL (~0.6–1.5 nM) |
| Plasma (standing) | ~300–600 pg/mL (orthostatic increase) |
| Neuroeffector junction (estimated) | ~560 pg/mL ≈ 3.3 nM during a 20 mmHg pressor response |

**Phasic peaks**:
| Condition | Measurement |
|---|---|
| Vagus nerve stimulation (rat, microdialysis) | +23–28% hippocampal NE; +39% cortical NE |
| Synaptic cleft during burst firing (estimated) | **µM range** (sufficient to activate α1 and β receptors) |
| Severe sympathetic activation / pheochromocytoma | Up to 9,000–10,000 pg/mL plasma |

### Receptors
All adrenergic receptors are GPCRs. NE affinity hierarchy: **α2 > α1 > β1 >> β2**.

**Alpha-1 (α1A, α1B, α1D) — Gq → ↑IP3/DAG; excitatory**:
- Brain: cortex, hippocampus, thalamus, basal ganglia.
- Increases neuronal excitability; promotes arousal/attention; stimulates cortical ACh release; enhances working memory consolidation in PFC.

**Alpha-2 (α2A, α2B, α2C) — Gi → ↓cAMP; inhibitory**:
- **Presynaptic somatodendritic autoreceptors** (on LC soma): reduce LC firing (key negative feedback).
- **Presynaptic terminal autoreceptors**: reduce NE release.
- **Postsynaptic in PFC** (high density, α2A): enhances working memory by suppressing cAMP (basis of guanfacine/clonidine in ADHD).
- α2A dominant in cortex/PFC; α2C in striatum/limbic.

**Beta-1 (β1) — Gs → ↑cAMP**:
- Cortex (moderate), hippocampus, cerebellum. Primary cardiac receptor (chronotropy/inotropy).
- CNS: facilitates LTP and memory consolidation; supports noradrenergic arousal.
- NE is a strong β1 agonist (similar potency to epinephrine).

**Beta-2 (β2) — Gs → ↑cAMP**:
- Cortex, cerebellum, astrocytes. NE is a **weak** β2 agonist (epinephrine far more potent).
- Vascular smooth muscle vasodilation.

**Receptor activation thresholds**:
- **Tonic low-nM NE**: primarily α2 autoreceptors → negative feedback dominant.
- **Moderate NE**: α1 and β1 activated → arousal and attention.
- **High NE (phasic bursts)**: all receptor classes activated, including β2.

### Receptor Sensitivity and Habituation
- **α2 autoreceptors**: chronic elevated NE (stress, PTSD) can desensitize these → reduced autoinhibitory feedback → runaway NE release.
- **β receptors**: rapid agonist-induced desensitization via GRK phosphorylation + β-arrestin (minutes to hours).
- **Chronic stress**: downregulates β1 in hippocampus/cortex; upregulates α1 → higher NE sensitivity, lower inhibition.
- **Antidepressants (NRIs, SNRIs, TCAs)**: chronic NE reuptake blockade → α2 autoreceptor downregulation over 2–4 weeks → higher net NE transmission (proposed mechanism of antidepressant action; mirrors 5-HT1A desensitization dynamics).

### CNS vs. Peripheral
**Dual**. LC-NE is the major CNS neuromodulator. Peripheral NE is the primary postganglionic sympathetic transmitter (heart, vasculature, lungs, GI, liver, kidneys, adipose). Separate pools; peripheral NE does not readily cross BBB.

### Reuptake and Degradation
**Primary clearance (~90%)**: **NET** (norepinephrine transporter, SLC6A2). Na⁺/Cl⁻-dependent. Target of SNRIs (venlafaxine, duloxetine), NRIs (atomoxetine), TCAs, cocaine (less selective than for DAT).

In the **PFC**: both NET and COMT contribute to NE clearance.
In the **hippocampus**: DAT provides compensatory NE clearance where NET density is low.

**Enzymatic degradation** (major metabolites: VMA and MHPG):
- **MAO + ALDH**: NE → DHMA → **VMA** (via COMT; primary urine metabolite for peripheral activation)
- **MAO + ALR**: NE → DHPG → **MHPG** (via COMT; principal brain-derived NE metabolite; ~50% of urinary NE metabolites; used in research to index LC activity)
- **COMT (extraneuronal)**: NE → normetanephrine → MHPG or VMA

### Half-Life
| Compartment | Half-Life |
|---|---|
| Synaptic cleft | Seconds (NET clearance within 2–10 sec) |
| Plasma | ~2–2.5 min (t½ ~2 min; MAO + COMT in liver/kidney/plasma) |
| CSF | Longer effective half-life (diffusion-limited from brain) |

### Key Brain Regions
- **Locus coeruleus** (synthesis; origin of all major NE projections)
- **Prefrontal cortex** (executive function, working memory; dense α2A postsynaptic; NET)
- **Hippocampus** (memory consolidation; β1, α2; emotional memory)
- **Amygdala** (fear conditioning, emotional arousal; β-adrenergic critical; propranolol in PTSD)
- **Thalamus** (sensory gating, sleep-wake transitions)
- **ACC and OFC** (send utility signals to LC to trigger phasic bursts)
- **Hypothalamus** (HPA axis activation, sympathetic outflow)
- **Brainstem / spinal cord** (autonomic regulation, pain modulation)

### Primary Effects on Mood and Behavior
- Arousal and wakefulness (tonic LC rate = arousal state)
- Attention and focus (moderate tonic NE = optimal task performance)
- Fight-or-flight (peripheral cardiovascular; central threat-detection priming)
- Working memory (postsynaptic α2A in PFC; inverted-U)
- Emotional memory consolidation (β1 and α1 in amygdala and hippocampus during arousing events — explains vivid emotional memories)
- Explore vs. exploit behavioral trade-off (Aston-Jones tonic-phasic model)
- HPA axis activation (LC → hypothalamus → CRH cascade)

### High NE Phenotype
Heightened alertness, sharp focus, rapid heart rate, elevated blood pressure, acute anxiety, hypervigilance, dry mouth, dilated pupils. Pathological excess: panic attacks (yohimbine provokes panic in ~70%, flashbacks in ~40% of PTSD patients), PTSD hyperarousal, mania.

### Low NE Phenotype
Fatigue, hypoarousal, drowsiness, difficulty concentrating, cognitive slowing, flat affect, lack of initiative. Depression with prominent fatigue/cognitive symptoms (vs. purely emotional depression of low serotonin). ADHD-like inattention (basis of atomoxetine/NRI treatment). Orthostatic hypotension; autonomic failure.

---

## Cross-System Interactions

- **DA and 5-HT opponent systems**: dopamine encodes positive RPE; serotonin may encode long-run average reward and negative RPE/punishment tolerance. Many antidepressants/antipsychotics target both simultaneously.
- **NE and DA co-release in PFC**: NET clears both NE and DA in PFC (no DAT there). NE and DA share molecular machinery and effects on PFC function.
- **NE facilitates raphe firing**: LC projects to DRN via α1 receptors, tonically driving serotonin neuron activity. Explains why SNRIs (blocking both NET and SERT) have antidepressant effects beyond SSRIs alone.
- **NE potentiates phasic DA**: LC activation can potentiate VTA burst firing, synergizing arousal-driven reward processing.
- **Autoreceptor desensitization analogy**: all three systems show analogous autoreceptor desensitization under chronic antidepressant treatment (D2, 5-HT1A/1B, α2), with 2–4 week timescales for therapeutic effect.
