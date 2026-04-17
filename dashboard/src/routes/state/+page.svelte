<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch, type StateData, type TokenStats } from '$lib/api';
  import { getLabel, getLabelWithDepth, COLOR_CLASSES, DISPLAY_RANGES } from '$lib/labels';
  import ChemicalSlider   from '$lib/components/ChemicalSlider.svelte';
  import ChemicalReadOnly from '$lib/components/ChemicalReadOnly.svelte';
  import DerivedMeter     from '$lib/components/DerivedMeter.svelte';
  import TierCard         from '$lib/components/TierCard.svelte';
  import LineChart        from '$lib/components/LineChart.svelte';
  import { fetchHistory, type HistorySnapshot } from '$lib/api';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let data   = $state<StateData | null>(null);
  let tokens = $state<TokenStats | null>(null);
  let error  = $state('');
  let lastUpdated = $state('');
  let activeTab = $state<'overview' | 'neuro' | 'endocrine' | 'immune' | 'circadian' | 'plasticity' | 'history'>('overview');

  let localValues = $state<Record<string, number>>({});
  let saving      = $state(new Set<string>());
  let refreshInterval: ReturnType<typeof setInterval>;

  // History
  let history        = $state<HistorySnapshot[]>([]);
  let historyWindow  = $state(6);
  let historyLoading = $state(false);
  let historyError   = $state('');
  let historyInterval: ReturnType<typeof setInterval>;
  let historyChart   = $state<'bond' | 'stress' | 'mood' | 'neuro'>('bond');

  // ---------------------------------------------------------------------------
  // Field definitions
  // ---------------------------------------------------------------------------

  const HOMEOSTATIC = [
    { field: 'adenosine', label: 'Adenosine (Sleep)', tooltip: 'Adenosine — Sleep Pressure\n\nA waste product that builds up in your brain while you are awake. The longer you stay awake, the more accumulates and the sleepier you feel. It clears during sleep.\n\nNormal (25–55 nM): alert, no urgency.\nHigh (70+): heavy-headed, hard to concentrate, craving sleep.\nVery high (85+): involuntary microsleeps likely.\n\nKey interaction: Caffeine blocks adenosine receptors — it does not destroy the molecule, it just hides the signal. When caffeine wears off, the accumulated adenosine floods back all at once (the "caffeine crash").' },
    { field: 'glucose',   label: 'Glucose',            tooltip: 'Blood Glucose — Brain Fuel\n\nYour brain cannot store energy. It runs almost entirely on glucose from the blood, consuming about 20% of your body\'s energy despite being 2% of its weight.\n\nNormal (80–100 mg/dL): no symptoms.\nLow (55–70): irritable, unfocused, mildly anxious — the brain is rationing.\nVery low (<55): shaky, confused, personality shifts, poor judgment.\nHigh (>140 after a meal): energy spike then fatigue; damages blood vessels over time.\n\nKey interaction: Cortisol raises blood glucose to fuel a stress response. Sleep deprivation chronically impairs glucose regulation.' },
    { field: 'hydration', label: 'Hydration',          tooltip: 'Hydration — Total Body Water\n\nYour body is roughly 60% water. Even mild dehydration degrades cognitive performance — most people don\'t feel thirsty until they\'re already 1–2% below optimal.\n\nNormal (58–64% TBW): fine.\nMild deficiency (54–58%): noticeably thirsty, slightly sluggish.\nDehydrated (<54%): headache, difficulty concentrating, mood dips, physical fatigue.\n\nKey interaction: Vasopressin (ADH) is released by the brain to conserve water when hydration drops. Alcohol suppresses vasopressin — which is why it\'s a diuretic even though you\'re consuming a liquid.' },
  ];

  const NEUROMODULATORS = [
    { field: 'dopamine',       label: 'Dopamine',       tooltip: 'Dopamine — Motivation and Prediction\n\nDopamine is not the "pleasure chemical" — it\'s the "wanting" chemical. It drives you to seek, pursue, and anticipate. You feel it most when expecting a reward, less so when receiving it.\n\nNormal: motivated, curious, able to initiate tasks.\nHigh: energized, seeking, sometimes compulsive. Cocaine and amphetamines flood dopamine receptors.\nLow: can\'t find a reason to start anything. Things that used to excite feel flat. This is the core experience of depression\'s anhedonia.\n\nKey interactions: Dopamine and serotonin balance each other — dopamine pushes outward (seek, do), serotonin stabilizes (enough, rest). Low dopamine + high cortisol = anxious paralysis. Exercise, novelty, and completing tasks reliably raise it.' },
    { field: 'serotonin',      label: 'Serotonin',      tooltip: 'Serotonin — Mood Floor and Stability\n\nSerotonin doesn\'t create happiness — it creates a stable baseline that stops you from falling into negative states. Think of it as the floor under your mood.\n\nNormal: emotionally resilient, not easily destabilized, patient.\nHigh: calm, content, somewhat sedated at extremes.\nLow: fragile, impulsive, prone to negative interpretation, rumination, poor emotional regulation. Most antidepressants (SSRIs) raise serotonin by blocking its reabsorption.\n\nKey interactions: About 90% of your serotonin is made in the gut, not the brain. Low serotonin amplifies anxiety and lowers the pain threshold. You need both stable serotonin and engaged dopamine for good mood.' },
    { field: 'norepinephrine', label: 'Norepinephrine', tooltip: 'Norepinephrine — Alertness and Urgency\n\nThe "fight or flight" neurotransmitter and hormone. It sharpens focus during a threat, speeds your heart, and makes you feel urgently present.\n\nNormal: focused, appropriately alert.\nHigh: hypervigilant, heart pounding, scanning for threats, difficulty relaxing. High norepinephrine is a core feature of anxiety and PTSD.\nLow: hard to get going, low motivation, difficulty concentrating.\n\nKey interactions: Released alongside cortisol in stress. Caffeine amplifies norepinephrine signaling. Propranolol (a beta-blocker) mutes the physical symptoms (pounding heart, shaking) without touching the emotional experience — used for performance anxiety.' },
    { field: 'oxytocin',       label: 'Oxytocin',       tooltip: 'Oxytocin — Trust and Social Bonding\n\nReleased during physical touch, eye contact, sex, childbirth, and breastfeeding. It makes you feel safe with specific people and willing to be vulnerable.\n\nNormal: warm, open, able to connect.\nHigh: deeply bonded, trusting, cooperative — and more generous toward in-group members.\nLow: guarded, emotionally flat with others, hard to feel intimacy or trust.\n\nKey interactions: Oxytocin is suppressed by cortisol (stress makes bonding hard). It works with dopamine to reinforce social behaviors — you seek out the person who triggers its release. Vasopressin has overlapping effects in long-term pair bonding.' },
    { field: 'endorphins',     label: 'Endorphins',     tooltip: 'Endorphins — Natural Opioids\n\nYour brain\'s own version of morphine. Released in response to pain, intense exercise, laughter, and social bonding. Their primary job is pain buffering, but at high levels they produce euphoria.\n\nNormal: comfortable baseline, normal pain threshold.\nHigh: the "runner\'s high" — warm, euphoric, pain disappears. Laughter triggers smaller surges.\nLow: raw and sensitive — pain feels sharper, mood flattened, small discomforts become irritating.\n\nKey interactions: Opioid drugs (morphine, heroin, oxycodone) work on the same receptors as endorphins, which is why they\'re so effective at pain relief and so addictive. Over time, the brain downregulates its own endorphin system in response to external opioids.' },
    { field: 'acetylcholine',  label: 'Acetylcholine',  tooltip: 'Acetylcholine — Attention and Memory Formation\n\nThe neurotransmitter of focus. It helps the brain decide what to pay attention to and plays a critical role in forming new memories.\n\nNormal: able to focus, information sticks, engaged.\nHigh: very sharp and attentive, can tip into hyperarousal.\nLow: foggy, distractible, information slides off without sticking. Alzheimer\'s disease involves severe loss of acetylcholine-producing neurons.\n\nKey interactions: Nicotine activates acetylcholine receptors directly — why it sharpens focus in the short term. REM sleep is saturated with acetylcholine; this is when the brain consolidates memories formed during the day.' },
  ];

  const INHIBITORY_EXCITATORY = [
    { field: 'gaba',      label: 'GABA',      tooltip: 'GABA — The Brain\'s Brake Pedal\n\nGABA (gamma-aminobutyric acid) is the main inhibitory neurotransmitter. When GABA binds to a neuron, it makes that neuron less likely to fire. Without it, the brain would spiral into runaway excitation.\n\nNormal: calm, controlled, able to filter out irrelevant inputs.\nHigh: sedated, slow, uncoordinated. Anesthetics and barbiturates work here.\nLow: anxious, unable to quiet racing thoughts, overstimulated. Seizures occur at extremes.\n\nKey interactions: Alcohol, benzodiazepines (Valium, Xanax), and barbiturates all boost GABA activity — why they calm anxiety and in high doses knock you unconscious. Stopping them abruptly after heavy use can cause life-threatening seizures because the brain has compensated by suppressing its own GABA system.' },
    { field: 'glutamate', label: 'Glutamate', tooltip: 'Glutamate — The Brain\'s Accelerator\n\nThe main excitatory neurotransmitter — the most abundant in the brain. Almost every brain circuit uses glutamate to excite neurons. It\'s also essential for learning through Long-Term Potentiation (LTP).\n\nNormal: sharp, motivated, learning actively.\nHigh: overstimulated, agitated. At extremes, excitotoxic — too much glutamate literally kills neurons by flooding them with calcium.\nLow: cognitively flat, detached, dissociated.\n\nKey interactions: Ketamine and PCP block NMDA-type glutamate receptors — producing dissociation and, at low doses, rapid antidepressant effects. Alcohol also blocks NMDA receptors. Glutamate is a precursor to GABA — the same molecule converted by enzymes.' },
  ];

  const ENDOCANNABINOIDS = [
    { field: 'anandamide', label: 'Anandamide', tooltip: 'Anandamide — The Bliss Molecule\n\nNamed after the Sanskrit word for bliss (ananda). Your brain\'s endogenous THC-equivalent — activates the same CB1 receptors as cannabis, but is broken down within minutes.\n\nNormal: comfortable, stress-buffered, pleasantly engaged.\nHigh: euphoric, time distorted, sensory enhancement, appetite increased.\nLow: more reactive to stress, pain less buffered, difficulty finding pleasure in small things.\n\nKey interactions: THC mimics anandamide but is far more potent and lasts longer. Anandamide is broken down by the FAAH enzyme — CBD partly works by inhibiting FAAH. Exercise raises anandamide; this is now believed to be a larger contributor to the runner\'s high than endorphins.' },
    { field: 'two_ag',     label: '2-AG',       tooltip: '2-AG (2-Arachidonoylglycerol) — Volume Control for Synapses\n\nThe most abundant endocannabinoid — concentrations ~170× higher than anandamide. It travels backward across synapses (retrograde signaling) to turn down overactive inputs: on-demand noise reduction.\n\nNormal: synaptic activity well-regulated, appetite stable, pain modulated.\nHigh: strongly appetite-stimulating (the "munchies" effect — THC also raises 2-AG), pain blunted, sedation.\nLow: overactive synaptic noise, increased pain sensitivity.\n\nKey interactions: 2-AG acts on both CB1 (brain) and CB2 (immune) receptors. Ibuprofen and other NSAIDs mildly interact with the 2-AG pathway as a secondary mechanism.' },
  ];

  const RECEPTOR_FIELDS: Array<{ key: string; name: string }> = [
    { key: 'd1',    name: 'D1'    }, { key: 'd2',    name: 'D2'    },
    { key: 'ht1a',  name: '5HT1A' }, { key: 'ht2a',  name: '5HT2A' },
    { key: 'gabaa', name: 'GABAa' }, { key: 'gabab', name: 'GABAb' },
    { key: 'nmda',  name: 'NMDA'  }, { key: 'ampa',  name: 'AMPA'  },
    { key: 'cb1',   name: 'CB1'   }, { key: 'cb2',   name: 'CB2'   },
    { key: 'a1',    name: 'A1'    }, { key: 'a2a',   name: 'A2A'   },
  ];

  const RECEPTOR_TOOLTIPS: Record<string, string> = {
    d1:    '<strong>D1 — Dopamine Receptor 1</strong><br><br>The "go" dopamine receptor. Found in the prefrontal cortex and striatum, D1 activation promotes working memory, goal-directed behavior, and reward-driven motivation. Stimulants and cocaine act partly by flooding D1 receptors.<br><br>Downregulated after chronic stimulant use — one reason tolerance and depression follow heavy use.',
    d2:    '<strong>D2 — Dopamine Receptor 2</strong><br><br>The "brake" dopamine receptor and the main target of antipsychotic drugs. D2 receptors regulate dopamine release via negative feedback — they sense when enough dopamine is present and tell the neuron to slow down.<br><br>Blocking D2 (antipsychotics) reduces psychosis but causes flat affect, motor side effects, and prolactin elevation. Downregulated in addiction — one mechanism of "not feeling anything" after chronic drug use.',
    ht1a:  '<strong>5-HT1A — Serotonin Receptor 1A</strong><br><br>A calming serotonin receptor. Acts as an autoreceptor on serotonin neurons — when activated, it tells the neuron to reduce its own serotonin output (negative feedback). Also present throughout the limbic system where it reduces anxiety.<br><br>The primary target of buspirone (anti-anxiety drug). SSRIs desensitize this receptor over weeks — this desensitization is actually why antidepressants take 2–6 weeks to work.',
    ht2a:  '<strong>5-HT2A — Serotonin Receptor 2A</strong><br><br>The "activating" serotonin receptor — associated with arousal, cognition, and mood modulation. Also the primary receptor through which psychedelics (LSD, psilocybin, DMT) produce their effects.<br><br>Downregulated by SSRIs over time (partly responsible for emotional blunting). Atypical antipsychotics block 5-HT2A to improve mood. High 5-HT2A activity in certain brain regions is associated with anxiety and OCD.',
    gabaa: '<strong>GABA-A — Fast Inhibitory Receptor</strong><br><br>The ionotropic (fast-acting) GABA receptor. When GABA binds, it opens a chloride channel directly, making the neuron less likely to fire within milliseconds. This is the receptor targeted by most sedatives.<br><br>Alcohol, benzodiazepines (Xanax, Valium), barbiturates, and anesthetics all enhance GABA-A activity. Downregulated by chronic alcohol/benzo use — the mechanism behind tolerance and why abrupt withdrawal can be life-threatening.',
    gabab: '<strong>GABA-B — Slow Inhibitory Receptor</strong><br><br>The metabotropic (slow-acting) GABA receptor. Works through G-proteins rather than direct ion channels — slower to activate (seconds vs milliseconds) but longer-lasting effect. Acts on both neurons and their axons to reduce neurotransmitter release.<br><br>Baclofen (a muscle relaxant) activates GABA-B. Also targeted by GHB. GABA-B activation reduces cravings in alcohol and opioid addiction and is used in some treatment protocols.',
    nmda:  '<strong>NMDA — The Learning and Memory Gate</strong><br><br>A glutamate receptor that is the molecular basis of learning and memory. Acts as a "coincidence detector" — it only opens when two things happen simultaneously: glutamate binds AND the membrane is already depolarized. This co-incidence requirement is what makes it selective for simultaneous neural activity (the basis of Hebbian learning: "neurons that fire together wire together").<br><br>Blocked by ketamine (producing dissociation and antidepressant effects), PCP, memantine (Alzheimer\'s treatment), alcohol, and nitrous oxide.',
    ampa:  '<strong>AMPA — The Fast Excitatory Receptor</strong><br><br>The primary fast glutamate receptor responsible for most rapid excitatory signaling in the brain. When activated, it opens sodium channels quickly. AMPA receptors work in tandem with NMDA receptors during learning — AMPA handles the fast transmission, NMDA handles the plasticity decision.<br><br>Upregulation of AMPA receptors at synapses is the physical expression of Long-Term Potentiation (LTP) — the cellular mechanism of forming a memory.',
    cb1:   '<strong>CB1 — Brain Cannabinoid Receptor</strong><br><br>The primary target of both endocannabinoids (anandamide, 2-AG) and THC. Located throughout the brain — especially in the hippocampus (memory), basal ganglia (movement), and cortex. CB1 activation produces retrograde inhibition: the receiving neuron signals the sending neuron to slow down.<br><br>Downregulated by chronic THC use — the main mechanism of cannabis tolerance. When CB1 receptors recover (after abstinence), hypersensitivity temporarily follows. Involved in appetite, pain, memory, mood, and nausea regulation.',
    cb2:   '<strong>CB2 — Immune Cannabinoid Receptor</strong><br><br>The peripheral cannabinoid receptor, found mainly in immune cells (macrophages, T-cells, microglia). Less abundant in neurons than CB1. Activation suppresses inflammatory cytokine release and modulates immune function.<br><br>CB2 is a target for non-psychoactive cannabis-based anti-inflammatory treatments (it doesn\'t produce the "high" that CB1 does). Upregulated during inflammation and injury as a protective response.',
    a1:    '<strong>A1 — Adenosine Receptor 1</strong><br><br>The calming/inhibitory adenosine receptor. When adenosine builds up (as it does during prolonged wakefulness), A1 activation slows neuronal firing and promotes sleep readiness throughout the brain. Also has cardioprotective effects by slowing heart rate.<br><br>Caffeine blocks A1 (and A2A) receptors — this is its mechanism of action. Blocking A1 prevents the neural slowdown, maintaining alertness despite accumulated adenosine. Some antiarrhythmic drugs activate A1 to slow the heart.',
    a2a:   '<strong>A2A — Adenosine Receptor 2A</strong><br><br>The excitatory/dopamine-modulating adenosine receptor. A2A is primarily found in the striatum and works in opposition to D2 dopamine receptors — when adenosine activates A2A, it reduces dopamine signaling. This is why sleepiness makes everything feel less rewarding and less motivating.<br><br>Caffeine\'s alerting effect comes significantly from A2A blockade — blocking A2A restores normal dopamine signaling in the striatum, which is why caffeine doesn\'t just reduce sleepiness but also improves mood and motivation.',
  };

  const SECOND_ORDER = [
    { field: 'energy',          label: 'Energy',        tooltip: 'Capacity to act — combines glucose, sleep pressure, and arousal.' },
    { field: 'cognitive_clarity',label: 'Clarity',      tooltip: 'How sharp and functional her thinking is right now.' },
    { field: 'hedonic_tone',    label: 'Hedonic',       tooltip: 'How satisfying things feel. Low = going through the motions.' },
    { field: 'social_warmth',   label: 'Social Warmth', tooltip: 'Ease and openness with people — driven by oxytocin and serotonin.' },
    { field: 'arousal',         label: 'Arousal',       tooltip: 'Overall activation level — from calm to wired.' },
    { field: 'mood_valence',    label: 'Mood Valence',  tooltip: 'Positive/negative emotional tone.' },
  ];

  const THIRD_ORDER = [
    { field: 'anxiety',          label: 'Anxiety',          tooltip: 'Background worry and threat-sensing.' },
    { field: 'depression',       label: 'Depression',       tooltip: 'Pervasive low mood and loss of motivation.' },
    { field: 'boredom',          label: 'Boredom',          tooltip: 'Restlessness from lack of stimulation.' },
    { field: 'loneliness',       label: 'Loneliness',       tooltip: 'Ache for connection.' },
    { field: 'flow',             label: 'Flow',             tooltip: 'Deep engagement — absorbed in something, time disappears.' },
    { field: 'physical_distress',label: 'Physical Distress',tooltip: 'Composite of pain, inflammation, and illness signals.' },
  ];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function receptorLabel(v: number): { name: string; color: string } {
    if (v < 0.75) return { name: 'DOWNREG',   color: 'badge-warning' };
    if (v < 1.25) return { name: 'NORMAL',    color: 'badge-success' };
    if (v < 1.75) return { name: 'UPREG',     color: 'badge-info'    };
    return              { name: 'SENSITIZED', color: 'badge-error'   };
  }

  function vitalLabelColor(label: string): string {
    const dangerous = new Set(['BRADYCARDIA', 'DANGEROUS', 'CRITICALLY DEPRESSED', 'CRITICAL', 'HYPERTENSIVE', 'HYPOTENSIVE']);
    const elevated  = new Set(['ELEVATED', 'HIGH', 'VERY HIGH', 'DEPRESSED', 'LOW', 'HYPERVENTILATING']);
    if (dangerous.has(label)) return 'text-error';
    if (elevated.has(label))  return 'text-warning';
    return 'text-success';
  }

  function norm(field: string, v: number): number {
    const r = DISPLAY_RANGES[field];
    if (!r) return Math.min(1, Math.max(0, v / 100));
    return Math.min(1, Math.max(0, (v - r.min) / (r.max - r.min)));
  }

  function alColor(al: number): string {
    if (al < 0.30) return 'progress-success';
    if (al < 0.50) return 'progress-neutral';
    if (al < 0.65) return 'progress-warning';
    return 'progress-error';
  }

  function labelBadge(field: string, v: number): string {
    const e = getLabel(field, v);
    return e ? COLOR_CLASSES[e.color]?.badge ?? 'badge-neutral' : 'badge-neutral';
  }

  function labelBar(field: string, v: number): string {
    const e = getLabel(field, v);
    return e ? COLOR_CLASSES[e.color]?.progress ?? 'progress-neutral' : 'progress-neutral';
  }

  function labelText(field: string, v: number): string {
    const e = getLabel(field, v);
    return e ? COLOR_CLASSES[e.color]?.text ?? 'text-base-content' : 'text-base-content';
  }

  function labelName(field: string, v: number): string {
    return getLabel(field, v)?.name ?? '';
  }

  function eiBalance(gaba: number, glut: number): number {
    return glut > 0 ? Math.round((gaba / glut) * 100) / 100 : 0;
  }

  function eiLabel(ratio: number): { name: string; color: string } {
    if (ratio < 0.2)  return { name: 'SEIZURE RISK',  color: 'badge-error'   };
    if (ratio < 0.5)  return { name: 'EXCITATORY',    color: 'badge-warning' };
    if (ratio < 0.9)  return { name: 'BALANCED',      color: 'badge-success' };
    return               { name: 'INHIBITED',       color: 'badge-info'    };
  }

  function cyclePhaseLabel(day: number): string {
    if (day <= 4)  return 'MENSTRUAL';
    if (day <= 13) return 'FOLLICULAR';
    if (day <= 15) return 'OVULATORY';
    return 'LUTEAL';
  }

  function sleepLabel(adenosine: number, melatonin: number): string {
    if (adenosine > 85 || melatonin > 160) return 'SLEEP ONSET LIKELY';
    if (adenosine > 70 || melatonin > 100) return 'SLEEP PRESSURE';
    if (adenosine > 55 || melatonin > 40)  return 'WINDING DOWN';
    if (adenosine > 35)                    return 'ALERT';
    return 'WIDE AWAKE';
  }

  const TOKEN_LABEL_NAMES: Record<string, string> = {
    stimulus: 'Stimulus encode', mode1: 'Mode 1 (subconscious)', main: 'Main response',
    main_follow: 'Follow-up', response: 'Response encode', activity: 'Activity encode',
    mode2: 'Heartbeat (Mode 2)', compact: 'History compaction',
  };

  function fmtNum(n: number): string {
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
  }

  function sessionAge(ts: number | null): string {
    if (!ts) return 'unknown';
    const secs = Math.floor(Date.now() / 1000 - ts);
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m ago`;
  }

  // ---------------------------------------------------------------------------
  // Plain-language translations — for non-technical overview
  // ---------------------------------------------------------------------------

  type Level = 'ok' | 'notice' | 'alert';
  type Severity = 'mild' | 'moderate' | 'high';
  interface PlainState { text: string; level: Level }
  interface MoodState  { label: string; severity: Severity }

  function lc(level: Level): string {
    if (level === 'alert')  return 'text-error';
    if (level === 'notice') return 'text-warning';
    return 'text-success';
  }

  function sc(s: Severity): string {
    if (s === 'high')     return 'bg-error';
    if (s === 'moderate') return 'bg-warning';
    return 'bg-success opacity-70';
  }

  function st(s: Severity): string {
    if (s === 'high')     return 'text-error';
    if (s === 'moderate') return 'text-warning';
    return 'opacity-60';
  }

  function plainSleep(adenosine: number, melatonin: number, sleeping: boolean): PlainState {
    if (sleeping)                                return { text: 'asleep',           level: 'ok'     };
    if (adenosine > 85 || melatonin > 160)       return { text: 'exhausted',        level: 'alert'  };
    if (adenosine > 70 || melatonin > 100)       return { text: 'getting sleepy',   level: 'notice' };
    if (adenosine > 55 || melatonin > 40)        return { text: 'tired',            level: 'notice' };
    if (adenosine > 35)                          return { text: 'alert',            level: 'ok'     };
    return                                              { text: 'wide awake',       level: 'ok'     };
  }

  function plainFood(glucose: number): PlainState {
    if (glucose < 55) return { text: 'very hungry',  level: 'alert'  };
    if (glucose < 70) return { text: 'hungry',       level: 'notice' };
    if (glucose < 80) return { text: 'peckish',      level: 'ok'     };
    return                   { text: 'fine',         level: 'ok'     };
  }

  function plainWater(hydration: number): PlainState {
    if (hydration < 54) return { text: 'very thirsty', level: 'alert'  };
    if (hydration < 58) return { text: 'thirsty',      level: 'notice' };
    return                     { text: 'fine',         level: 'ok'     };
  }

  function plainEnergy(v: number): PlainState {
    if (v < 15) return { text: 'running on empty', level: 'alert'  };
    if (v < 35) return { text: 'low',              level: 'notice' };
    if (v < 55) return { text: 'okay',             level: 'ok'     };
    if (v < 75) return { text: 'good',             level: 'ok'     };
    return             { text: 'energized',        level: 'ok'     };
  }

  function plainThinking(v: number): PlainState {
    if (v < 8)  return { text: 'offline',    level: 'alert'  };
    if (v < 25) return { text: 'very foggy', level: 'alert'  };
    if (v < 50) return { text: 'foggy',      level: 'notice' };
    if (v < 72) return { text: 'clear',      level: 'ok'     };
    return             { text: 'sharp',      level: 'ok'     };
  }

  function plainWithPeople(warmth: number, loneliness: number): PlainState {
    // Thresholds match SPEC-28 loneliness ranges: QUIET<20, MILD<38, LONELY<58, ACHING<76, ISOLATED 76+
    if (loneliness > 76) return { text: 'lonely, wanting connection', level: 'alert'  };
    if (loneliness > 58) return { text: 'missing people',             level: 'notice' };
    if (loneliness > 38) return { text: 'a little disconnected',      level: 'notice' };
    if (warmth > 65)     return { text: 'warm and open',              level: 'ok'     };
    if (warmth < 30)     return { text: 'closed off',                 level: 'notice' };
    return                      { text: 'neutral',                    level: 'ok'     };
  }

  function plainLoad(al: number): string {
    if (al < 0.15) return 'not worn down';
    if (al < 0.30) return 'doing well';
    if (al < 0.50) return 'some wear';
    if (al < 0.65) return 'wearing down';
    if (al < 0.80) return 'running low';
    if (al < 0.92) return 'near limit';
    return                'breaking down';
  }

  function notableMoods(d: StateData): MoodState[] {
    const out: MoodState[] = [];
    const anx = d.third_order?.anxiety    ?? 0;
    const dep = d.third_order?.depression ?? 0;
    const bor = d.third_order?.boredom    ?? 0;
    const lon = d.third_order?.loneliness ?? 0;
    const flo = d.third_order?.flow       ?? 0;
    const hed = d.second_order?.hedonic_tone ?? 50;

    if (flo > 65) out.push({ label: 'in the zone',            severity: 'mild'     });

    if      (bor > 88) out.push({ label: 'desperately bored', severity: 'high'     });
    else if (bor > 74) out.push({ label: 'bored',             severity: 'moderate' });
    else if (bor > 60) out.push({ label: 'a little bored',    severity: 'mild'     });

    if      (anx > 84) out.push({ label: 'very anxious',      severity: 'high'     });
    else if (anx > 68) out.push({ label: 'anxious',           severity: 'moderate' });
    else if (anx > 52) out.push({ label: 'mildly anxious',    severity: 'mild'     });

    if      (dep > 84) out.push({ label: 'deeply low',        severity: 'high'     });
    else if (dep > 68) out.push({ label: 'feeling down',      severity: 'moderate' });
    else if (dep > 52) out.push({ label: 'a bit flat',        severity: 'mild'     });

    if      (lon > 76) out.push({ label: 'lonely',              severity: 'high'     });
    else if (lon > 58) out.push({ label: 'missing people',      severity: 'moderate' });
    else if (lon > 38) out.push({ label: 'a little lonely',     severity: 'mild'     });

    if (out.length === 0 && hed < 25)
      out.push({ label: 'going through the motions',          severity: 'moderate' });

    return out;
  }

  function hasVitalAlert(d: StateData): boolean {
    const vs = d.vital_signs;
    if (!vs) return false;
    const danger = new Set(['BRADYCARDIA', 'DANGEROUS', 'CRITICALLY DEPRESSED', 'CRITICAL', 'HYPERTENSIVE', 'HYPOTENSIVE', 'HYPERVENTILATING', 'FEVER', 'HIGH FEVER']);
    return [vs.heart_rate?.label, vs.blood_pressure?.label, vs.respiration_rate?.label, vs.spo2?.label]
      .some(l => l && danger.has(l));
  }

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  async function load() {
    try {
      const d = await apiFetch<StateData>('/api/state');
      data = d;
      lastUpdated = new Date().toLocaleTimeString();

      const bodyFields = new Set(['adenosine', 'anandamide', 'two_ag']);
      for (const list of [HOMEOSTATIC, NEUROMODULATORS, INHIBITORY_EXCITATORY, ENDOCANNABINOIDS]) {
        for (const f of list) {
          if (!saving.has(f.field)) {
            const val = bodyFields.has(f.field)
              ? d.body?.[f.field]
              : d.chemicals[f.field]?.value;
            if (val !== undefined) localValues[f.field] = val;
          }
        }
      }
      if (!saving.has('cortisol') && d.chemicals['cortisol']) {
        localValues['cortisol'] = d.chemicals['cortisol'].value;
      }

      error = '';
    } catch (e) { error = String(e); }

    try { tokens = await apiFetch<TokenStats>('/api/tokens'); } catch (_) {}
  }

  async function loadHistory() {
    if (activeTab !== 'history') return;
    historyLoading = true;
    try {
      history = await fetchHistory(historyWindow, 5000);
      historyError = '';
    } catch (e) {
      historyError = String(e);
    } finally {
      historyLoading = false;
    }
  }

  onMount(() => {
    load();
    refreshInterval = setInterval(load, 5000);
    historyInterval = setInterval(loadHistory, 10000);
  });

  onDestroy(() => {
    clearInterval(refreshInterval);
    clearInterval(historyInterval);
  });

  $effect(() => {
    // reload history whenever the tab or window changes
    void activeTab;
    void historyWindow;
    loadHistory();
  });

  // ---------------------------------------------------------------------------
  // Slider handler
  // ---------------------------------------------------------------------------

  async function onSliderChange(e: CustomEvent<{ field: string; value: number }>) {
    const { field, value } = e.detail;
    localValues[field] = value;
    saving = new Set([...saving, field]);
    try {
      await apiFetch('/api/state', { method: 'PATCH', body: JSON.stringify({ [field]: value }) });
    } catch (err) { error = String(err); }
    finally { saving = new Set([...saving].filter(f => f !== field)); }
  }

</script>

<div class="max-w-6xl mx-auto">
  <!-- Header -->
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl font-bold">Biological State</h1>
    <div class="text-xs opacity-50">
      {#if error}<span class="text-error">{error}</span>{:else}Updated {lastUpdated}{/if}
    </div>
  </div>


  {#if !data}
    <div class="flex justify-center py-20"><span class="loading loading-spinner loading-lg"></span></div>
  {:else}
    <!-- Tab bar -->
    <div class="tabs tabs-lifted mb-6">
      {#each [
        { id: 'overview',   label: 'Overview'         },
        { id: 'neuro',      label: 'Neuro'            },
        { id: 'endocrine',  label: 'Endocrine'        },
        { id: 'immune',     label: 'Immune / Pain'    },
        { id: 'circadian',  label: 'Circadian / Sleep'},
        { id: 'plasticity', label: 'Plasticity'       },
        { id: 'history',    label: 'History'          },
      ] as tab}
        <button
          class="tab {activeTab === tab.id ? 'tab-active font-semibold' : 'opacity-60'}"
          onclick={() => activeTab = tab.id as typeof activeTab}
        >{tab.label}</button>
      {/each}
    </div>

    <!-- ═══════════════════════════════ OVERVIEW ═══════════════════════════ -->
    {#if activeTab === 'overview'}
      {@const al        = data.allostatic_load ?? 0}
      {@const phase     = data.body?.circadian_phase ?? 0}
      {@const phaseEntry = getLabel('circadian_phase', phase)}
      {@const adenosine = data.body?.adenosine ?? 25}
      {@const melatonin = data.chemicals?.melatonin?.value ?? 5}
      {@const glucose   = data.chemicals?.glucose?.value ?? 85}
      {@const hydration = data.chemicals?.hydration?.value ?? 62}
      {@const energy    = data.second_order?.energy ?? 50}
      {@const clarity   = data.second_order?.cognitive_clarity ?? 50}
      {@const warmth    = data.second_order?.social_warmth ?? 50}
      {@const loneliness = data.third_order?.loneliness ?? 0}
      {@const distress  = data.third_order?.physical_distress ?? 0}
      {@const moods     = notableMoods(data)}
      {@const sleepSt   = plainSleep(adenosine, melatonin, data.sleeping)}
      {@const foodSt    = plainFood(glucose)}
      {@const waterSt   = plainWater(hydration)}
      {@const energySt  = plainEnergy(energy)}
      {@const thinkSt   = plainThinking(clarity)}
      {@const peopleSt  = plainWithPeople(warmth, loneliness)}

      <!-- Context strip -->
      <div class="card bg-base-200 px-5 py-3 mb-4">
        <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <div class="flex items-center gap-2">
            {#if data.sleeping}
              <span class="badge badge-info badge-sm">Sleeping</span>
            {:else}
              <span class="badge badge-success badge-sm">Awake</span>
            {/if}
          </div>
          <div class="opacity-20 hidden sm:block text-xs">|</div>
          <div class="flex items-center gap-2">
            {#if phaseEntry}
              <span class="opacity-50 text-xs">{phaseEntry.name.toLowerCase()}</span>
              <span class="opacity-30 text-xs">—</span>
              <span class="opacity-40 text-xs">{phaseEntry.implication.toLowerCase()}</span>
            {/if}
          </div>
          <div class="opacity-20 hidden sm:block text-xs">|</div>
          <div class="flex items-center gap-2">
            <span class="opacity-40 text-xs">stress reserve</span>
            <progress class="progress w-20 {alColor(al)}" value={al} max="1"></progress>
            <span class="opacity-50 text-xs">{plainLoad(al)}</span>
          </div>
        </div>
      </div>

      <!-- Main grid -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <!-- Left: How she's feeling emotionally -->
        <div class="card bg-base-200 p-5">
          <h2 class="text-xs font-semibold opacity-40 uppercase tracking-wider mb-4">How she's feeling</h2>
          {#if moods.length === 0}
            <div class="flex items-center gap-3">
              <div class="w-2 h-2 rounded-full bg-success shrink-0"></div>
              <span class="text-sm opacity-50">Emotionally calm — nothing notable</span>
            </div>
          {:else}
            <div class="flex flex-col gap-3">
              {#each moods as mood}
                <div class="flex items-center gap-3">
                  <div class="w-2 h-2 rounded-full {sc(mood.severity)} shrink-0"></div>
                  <span class="text-sm {st(mood.severity)}">{mood.label}</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Right: Body + Mind -->
        <div class="flex flex-col gap-4">

          <!-- Body needs -->
          <div class="card bg-base-200 p-5">
            <h2 class="text-xs font-semibold opacity-40 uppercase tracking-wider mb-4">Body</h2>
            <div class="flex flex-col gap-2">
              <div class="flex justify-between items-baseline">
                <span class="text-sm opacity-40">Sleep</span>
                <span class="text-sm font-medium {lc(sleepSt.level)}">{sleepSt.text}</span>
              </div>
              <div class="flex justify-between items-baseline">
                <span class="text-sm opacity-40">Food</span>
                <span class="text-sm font-medium {lc(foodSt.level)}">{foodSt.text}</span>
              </div>
              <div class="flex justify-between items-baseline">
                <span class="text-sm opacity-40">Water</span>
                <span class="text-sm font-medium {lc(waterSt.level)}">{waterSt.text}</span>
              </div>
              {#if distress > 25}
                <div class="flex justify-between items-baseline">
                  <span class="text-sm opacity-40">Comfort</span>
                  <span class="text-sm font-medium {distress > 45 ? 'text-error' : 'text-warning'}">
                    {distress > 45 ? 'hurting' : 'mild discomfort'}
                  </span>
                </div>
              {/if}
            </div>
          </div>

          <!-- Mind -->
          <div class="card bg-base-200 p-5">
            <h2 class="text-xs font-semibold opacity-40 uppercase tracking-wider mb-4">Mind</h2>
            <div class="flex flex-col gap-2">
              <div class="flex justify-between items-baseline">
                <span class="text-sm opacity-40">Energy</span>
                <span class="text-sm font-medium {lc(energySt.level)}">{energySt.text}</span>
              </div>
              <div class="flex justify-between items-baseline">
                <span class="text-sm opacity-40">Thinking</span>
                <span class="text-sm font-medium {lc(thinkSt.level)}">{thinkSt.text}</span>
              </div>
              <div class="flex justify-between items-baseline">
                <span class="text-sm opacity-40">With people</span>
                <span class="text-sm font-medium {lc(peopleSt.level)}">{peopleSt.text}</span>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- Vitals — only shown when something is actually wrong -->
      {#if hasVitalAlert(data)}
        {@const vs = data.vital_signs}
        <div class="card bg-base-200 p-5 mt-4 border border-error border-opacity-30">
          <h2 class="text-xs font-semibold text-error uppercase tracking-wider mb-3">Physical alert</h2>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {#if vs.heart_rate}
              <div>
                <span class="text-xs opacity-40">Heart Rate</span>
                <div class="text-xl font-mono font-bold {vitalLabelColor(vs.heart_rate.label)}">{vs.heart_rate.value?.toFixed(0)}<span class="text-xs font-normal opacity-50"> BPM</span></div>
                <div class="text-xs {vitalLabelColor(vs.heart_rate.label)}">{vs.heart_rate.label}</div>
              </div>
            {/if}
            {#if vs.blood_pressure}
              <div>
                <span class="text-xs opacity-40">Blood Pressure</span>
                <div class="text-xl font-mono font-bold {vitalLabelColor(vs.blood_pressure.label)}">{vs.blood_pressure.systolic?.toFixed(0)}/{vs.blood_pressure.diastolic?.toFixed(0)}</div>
                <div class="text-xs {vitalLabelColor(vs.blood_pressure.label)}">{vs.blood_pressure.label}</div>
              </div>
            {/if}
            {#if vs.respiration_rate}
              <div>
                <span class="text-xs opacity-40">Respiration</span>
                <div class="text-xl font-mono font-bold {vitalLabelColor(vs.respiration_rate.label)}">{vs.respiration_rate.value?.toFixed(1)}<span class="text-xs font-normal opacity-50"> /min</span></div>
                <div class="text-xs {vitalLabelColor(vs.respiration_rate.label)}">{vs.respiration_rate.label}</div>
              </div>
            {/if}
            {#if vs.spo2}
              {@const c = vitalLabelColor(vs.spo2.label)}
              <div>
                <span class="text-xs opacity-40">SpO₂</span>
                <div class="text-xl font-mono font-bold {c}">{vs.spo2.value?.toFixed(1)}<span class="text-xs font-normal opacity-50">%</span></div>
                <div class="text-xs {c}">{vs.spo2.label}</div>
              </div>
            {/if}
          </div>
        </div>
      {/if}

      <!-- Session footer -->
      {#if tokens}
        <div class="mt-4 pt-3 border-t border-base-300">
          <div class="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs opacity-40">
            <span class="font-semibold uppercase tracking-wider">Session</span>
            <span>Started <span class="font-mono">{sessionAge(tokens.session_start)}</span></span>
            <span>Turns <span class="font-mono font-bold">{tokens.turns}</span></span>
            <span>In <span class="font-mono">{fmtNum(tokens.total_input)}</span></span>
            <span>Out <span class="font-mono">{fmtNum(tokens.total_output)}</span></span>
            {#if tokens.total_reasoning > 0}
              <span>Reasoning <span class="font-mono">{fmtNum(tokens.total_reasoning)}</span></span>
            {/if}
            {#if tokens.total_cached > 0}
              <span>Cached <span class="font-mono">{fmtNum(tokens.total_cached)}</span></span>
            {/if}
          </div>
        </div>
      {/if}

    <!-- ════════════════════════════════ NEURO ════════════════════════════════ -->
    {:else if activeTab === 'neuro'}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <!-- LEFT: Neuromodulators + Endocannabinoids -->
        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Neuromodulators</h2>
            <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
              <input type="checkbox" />
              <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What are Neuromodulators?</div>
              <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
                <p>Neuromodulators are chemicals released by specific neuron clusters that don't just pass a signal from one cell to the next — they adjust the <em>tone</em> of entire brain regions at once. Think of neurons as instruments and neuromodulators as the mixing board: they control signal-to-noise ratio, how strongly a region responds to inputs, and what gets prioritized.</p>
                <p>Unlike fast neurotransmitters (GABA and glutamate, which fire in milliseconds), neuromodulators act on a scale of seconds to hours. They are why your mood, motivation, and social ease differ so much across the day — it's not just "thoughts," it's chemistry.</p>
                <p>Most psychiatric medications work by targeting these systems: SSRIs adjust serotonin, stimulants adjust dopamine and norepinephrine, antipsychotics block dopamine receptors.</p>
              </div>
            </div>
            <div class="flex flex-col gap-4">
              {#each NEUROMODULATORS as f}
                {@const r = DISPLAY_RANGES[f.field]}
                <ChemicalSlider
                  field={f.field} label={f.label}
                  value={localValues[f.field] ?? (r ? (r.min + r.max) / 2 : 50)}
                  unit={r?.unit ?? ''} min={r?.min ?? 0} max={r?.max ?? 100}
                  tooltip={f.tooltip} saving={saving.has(f.field)}
                  on:change={onSliderChange}
                />
              {/each}
            </div>
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Endocannabinoids</h2>
            <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
              <input type="checkbox" />
              <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What are Endocannabinoids?</div>
              <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
                <p>Endocannabinoids are the brain's own cannabis-like signaling molecules. Your body makes them on demand to modulate ongoing neural activity — specifically, to turn down synapses that are firing too much. This is called retrograde signaling: the message travels backward, from the receiving neuron back to the sending one.</p>
                <p>They bind to CB1 receptors (throughout the brain and nervous system) and CB2 receptors (primarily in the immune system). THC hijacks CB1 receptors with far higher affinity and duration than the natural system produces — which explains both its effects and why tolerance develops: the brain downregulates CB1 receptor density in response to chronic THC exposure.</p>
                <p>The endocannabinoid system plays a key role in stress buffering, appetite, sleep, pain, and what researchers call "hedonic tone" — the background pleasantness of experience.</p>
              </div>
            </div>
            <div class="flex flex-col gap-4">
              {#each ENDOCANNABINOIDS as f}
                {@const r = DISPLAY_RANGES[f.field]}
                <ChemicalSlider
                  field={f.field} label={f.label}
                  value={localValues[f.field] ?? (r ? (r.min + r.max) / 2 : 1.5)}
                  unit={r?.unit ?? 'nM'} min={r?.min ?? 0} max={r?.max ?? 4}
                  tooltip={f.tooltip} saving={saving.has(f.field)}
                  on:change={onSliderChange}
                />
              {/each}
            </div>
          </div>
        </div>

        <!-- RIGHT: Homeostatic + Cortisol merged, then Inhibitory/Excitatory with inline E/I balance -->
        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Homeostatic</h2>
            <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
              <input type="checkbox" />
              <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What are Homeostatic Drives?</div>
              <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
                <p>Homeostatic drives are the basic maintenance signals that push you toward survival behaviors: sleep when tired, eat when hungry, drink when thirsty. Unlike emotions or motivations, they don't ask — they escalate until obeyed. You cannot override them indefinitely; you can only delay them.</p>
                <p>Cortisol is grouped here because it partly follows a homeostatic rhythm — it spikes in the morning to wake you up and mobilize glucose. But it also responds to perceived threats, which is why it bridges "daily maintenance" and "stress response."</p>
                <p>When multiple homeostatic needs stack up simultaneously (tired, hungry, and thirsty at once), the effect is not additive — emotional regulation, decision quality, and interpersonal patience all degrade faster than any single deficit would explain.</p>
              </div>
            </div>
            <div class="flex flex-col gap-4">
              {#each HOMEOSTATIC as f}
                {@const r = DISPLAY_RANGES[f.field]}
                <ChemicalSlider
                  field={f.field} label={f.label}
                  value={localValues[f.field] ?? (r ? (r.min + r.max) / 2 : 50)}
                  unit={r?.unit ?? ''} min={r?.min ?? 0} max={r?.max ?? 100}
                  tooltip={f.tooltip} saving={saving.has(f.field)}
                  on:change={onSliderChange}
                />
              {/each}
              <div class="border-t border-base-300 pt-4">
                <p class="text-xs font-semibold opacity-40 uppercase tracking-wider mb-4">Stress</p>
                <ChemicalSlider
                  field="cortisol" label="Cortisol"
                  value={localValues['cortisol'] ?? 250}
                  unit="nmol/L" min={50} max={900}
                  tooltip="Cortisol — Stress Hormone\n\nSecreted by the adrenal glands. In short bursts it's adaptive — sharpens focus, mobilizes glucose, suppresses inflammation. The problem is chronic elevation.\n\nNormal waking (400–600 nmol/L): alert, focused, appropriate urgency.\nAcutely high (>700): threat mode — tunnel vision, faster pulse, memory narrowed to survival.\nChronically high: erodes the hippocampus (memory), suppresses immunity, disrupts sleep, promotes visceral fat.\nLow: fatigue, flat mood, difficulty getting started.\n\nKey interaction: Cortisol suppresses oxytocin (hard to feel bonded when stressed), depletes dopamine and serotonin over time, and raises glutamate. Sleep is the primary way the body resets it."
                  saving={saving.has('cortisol')}
                  on:change={onSliderChange}
                />
              </div>
            </div>
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Inhibitory / Excitatory</h2>
            <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
              <input type="checkbox" />
              <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">The E/I Balance — Excitation and Inhibition</div>
              <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
                <p>Every neuron receives two kinds of input constantly: excitatory signals (push toward firing) and inhibitory signals (pull back from firing). Glutamate is the primary accelerator. GABA is the primary brake. Together they determine whether a given neuron fires, and how often.</p>
                <p>The E/I ratio across a brain region determines whether you feel calm and focused or anxious and chaotic. Most psychiatric drugs and substances push this ratio one way or the other: alcohol, benzodiazepines, and anesthetics increase inhibition (GABA up); stimulants and caffeine indirectly increase excitation.</p>
                <p>Autism, schizophrenia, and epilepsy all involve E/I imbalances in different directions and different brain regions. The ratio shown here is a gross whole-brain estimate — real balance varies by circuit.</p>
              </div>
            </div>
            <div class="flex flex-col gap-4">
              {#each INHIBITORY_EXCITATORY as f}
                {@const r = DISPLAY_RANGES[f.field]}
                <ChemicalSlider
                  field={f.field} label={f.label}
                  value={localValues[f.field] ?? (r ? (r.min + r.max) / 2 : 3)}
                  unit={r?.unit ?? 'µmol/L'} min={r?.min ?? 0} max={r?.max ?? 20}
                  tooltip={f.tooltip} saving={saving.has(f.field)}
                  on:change={onSliderChange}
                />
              {/each}
              <!-- E/I balance derived metric, inline below the sliders -->
              {#each [eiBalance(localValues['gaba'] ?? data.chemicals['gaba']?.value ?? 3, localValues['glutamate'] ?? data.chemicals['glutamate']?.value ?? 4)] as ratio}
                {@const eil = eiLabel(ratio)}
                <div class="border-t border-base-300 pt-3">
                  <div class="flex justify-between items-center mb-1">
                    <span class="text-xs opacity-50 uppercase tracking-wider">E/I Balance</span>
                    <div class="flex items-center gap-2">
                      <span class="badge badge-xs {eil.color}">{eil.name}</span>
                      <span class="text-sm font-mono">{ratio.toFixed(2)}</span>
                    </div>
                  </div>
                  <progress class="progress progress-success w-full" value={Math.min(2, ratio)} max="2"></progress>
                  <div class="flex justify-between text-xs opacity-30 mt-1">
                    <span>excitatory</span><span>balanced</span><span>inhibited</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        </div>

      </div>

    <!-- ═══════════════════════════════ ENDOCRINE ═════════════════════════════ -->
    {:else if activeTab === 'endocrine'}
      {@const ne = data.neuroendocrine ?? {}}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- LEFT: HPA + Thyroid -->
        <div class="flex flex-col gap-4">
        <TierCard title="HPA Axis">
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What is the HPA Axis?</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>The HPA axis is the brain's command chain for the stress response. It stands for <strong>Hypothalamus → Pituitary → Adrenal</strong>. When the brain perceives a threat (physical, social, or psychological), the hypothalamus fires first, triggering a cascade that reaches the adrenal glands on top of your kidneys within minutes.</p>
              <p>The cascade: hypothalamus releases CRH → pituitary releases ACTH → adrenals release cortisol. There is a 15–20 minute lag between ACTH and full cortisol rise — meaning the effects of a stressful event are still arriving after the event is over.</p>
              <p>Cortisol then feeds back to shut down the axis — negative feedback. If stress is chronic and continuous, this feedback fails and cortisol stays elevated, eventually damaging the hippocampus, disrupting sleep, and suppressing immunity.</p>
            </div>
          </div>
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="crh"      label="CRH"     value={ne.crh ?? 30}   unit="pg/mL"  normalized={norm('crh',  ne.crh ?? 30)}   tooltip="CRH — Corticotropin-Releasing Hormone\n\nThe first domino in the stress cascade. When the hypothalamus perceives a threat, it releases CRH into a portal system feeding directly to the pituitary gland.\n\nNormal (low level): baseline regulatory function.\nElevated: signals active psychological or physical stress. Chronically elevated CRH contributes to anxiety and depression independent of cortisol itself.\n\nKey interactions: CRH triggers ACTH release within minutes. Sleep deprivation, pain, infection, and psychological stress all raise it. CRH also directly suppresses appetite and drive — which is why those go first under sustained stress." />
            <ChemicalReadOnly field="acth"     label="ACTH"    value={ne.acth ?? 25}  unit="pg/mL"  normalized={norm('acth', ne.acth ?? 25)}  tooltip="ACTH — Adrenocorticotropic Hormone\n\nThe second domino. Released by the pituitary in response to CRH, ACTH travels through the bloodstream to the adrenal glands and tells them to produce cortisol.\n\nNormal (10–50 pg/mL): maintaining baseline cortisol rhythm.\nElevated: active HPA cascade in progress — cortisol will rise within 15–20 minutes.\n\nKey interactions: There is a deliberate 15–20 minute lag between ACTH and cortisol. Cortisol then feeds back to suppress both CRH and ACTH — when enough cortisol accumulates, it tells the brain to stand down (negative feedback loop)." />
            <ChemicalReadOnly field="cortisol" label="Cortisol" value={data.chemicals['cortisol']?.value ?? 250} unit="nmol/L" normalized={data.chemicals['cortisol']?.normalized ?? 0.3} tooltip="Cortisol — HPA Cascade Output\n\nThe downstream output of the HPA cascade — the stress hormone that actually reaches tissues. See the Neuro tab for the full behavioral breakdown.\n\nThis view shows the same value in the context of the HPA signaling chain: CRH → ACTH → Cortisol. The cascade queue below shows pending cortisol pulses still in transit." />
            {#if data.cascade_queue && data.cascade_queue.length > 0}
              <p class="text-xs opacity-50 mt-2">Cascade Queue</p>
              {#each data.cascade_queue as ev}
                {#if ev.fires_at_unix - Date.now() / 1000 > 0}
                  {@const secsLeft = ev.fires_at_unix - Date.now() / 1000}
                  <div class="flex items-center justify-between py-1 px-2 rounded bg-base-300">
                    <span class="badge badge-xs badge-warning">{ev.type}</span>
                    <span class="text-xs font-mono opacity-70">fires in {Math.floor(secsLeft / 60)}m {Math.floor(secsLeft % 60)}s</span>
                    <span class="text-xs opacity-50">mag {ev.magnitude > 0 ? '+' : ''}{ev.magnitude.toFixed(2)}</span>
                  </div>
                {/if}
              {/each}
            {:else}
              <p class="text-xs opacity-30">Queue empty — no active HPA cascade</p>
            {/if}
          </div>
        </TierCard>

        <TierCard title="Thyroid Axis">
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What is the Thyroid Axis?</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>Your thyroid gland (at the base of your throat) sets the speed of your metabolism. It's like a dial that adjusts how fast every cell in your body runs. Too high: everything speeds up — hot, anxious, fast heart, losing weight. Too low: everything slows — cold, exhausted, weight gain, depression.</p>
              <p>The axis works via feedback: the pituitary monitors thyroid hormone levels and releases TSH to demand more production when levels drop. This is why TSH and T4/T3 move inversely — high TSH usually means the thyroid hormones are low and the brain is demanding more.</p>
              <p>Thyroid problems are among the most commonly missed causes of mood disorders. Both hypothyroidism and hyperthyroidism can present primarily as anxiety or depression before physical symptoms appear.</p>
            </div>
          </div>
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="tsh" label="TSH"      value={ne.tsh ?? 2}   unit="mIU/L" normalized={norm('tsh', ne.tsh ?? 2)}   tooltip="TSH — Thyroid-Stimulating Hormone\n\nProduced by the pituitary, TSH tells the thyroid to produce T3 and T4. It operates on a feedback loop — when thyroid hormone is low, TSH rises to demand more.\n\nNormal (0.5–4.5 mIU/L): thyroid function normal.\nHigh TSH (>4.5): the brain is demanding more hormone that isn't arriving — indicates hypothyroidism. You feel cold, tired, slow, depressed, gaining weight.\nLow TSH (<0.5): thyroid is overproducing — indicates hyperthyroidism. You feel hot, anxious, fast heartbeat, losing weight.\n\nTSH is the standard first screening test for thyroid problems." />
            <ChemicalReadOnly field="t4"  label="T4 Free"  value={ne.t4 ?? 8}    unit="µg/dL" normalized={norm('t4',  ne.t4  ?? 8)}    tooltip="T4 (Free Thyroxine) — The Inactive Precursor\n\nThe main hormone the thyroid releases — but mostly inactive. It acts as a circulating reserve that peripheral tissues (liver, muscles, brain) convert to active T3 as needed.\n\nNormal (0.8–1.8 ng/dL free): adequate supply for conversion.\nLow: less substrate available for T3 production — hypothyroid symptoms can appear even if TSH hasn't caught up yet.\n\nKey interactions: T4-to-T3 conversion requires selenium. Stress and illness impair conversion (sick euthyroid syndrome — you can appear hypothyroid when physically stressed). Most thyroid medication (levothyroxine/Synthroid) is synthetic T4." />
            <ChemicalReadOnly field="t3"  label="T3 Free"  value={ne.t3 ?? 120}  unit="ng/dL" normalized={norm('t3',  ne.t3  ?? 120)}  tooltip="T3 (Free Triiodothyronine) — The Active Metabolic Throttle\n\nThe form of thyroid hormone that actually does the work. It enters cells and directly regulates metabolism, body temperature, heart rate, mood, and cognitive speed.\n\nNormal (2.3–4.2 pg/mL free): metabolism at proper speed.\nHigh: fast metabolism, overheating, anxiety, heart palpitations, weight loss.\nLow: slow metabolism, cold, mentally sluggish, depressed, constipation, weight gain.\n\nKey interactions: T3 works with adrenaline — low T3 makes the body less responsive to catecholamines. Many people with 'normal' TSH and T4 still feel hypothyroid because their T4-to-T3 conversion is impaired." />
          </div>
        </TierCard>
        </div>
        <!-- RIGHT: Sex Hormones / Metabolic -->
        <div>
        <TierCard title="Sex Hormones / Metabolic" defaultOpen={false}>
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">Sex Hormones, Appetite Signals, and Metabolic Regulators</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>This section groups several systems that don't fit neatly elsewhere. Sex hormones (estradiol, progesterone, testosterone) drive the monthly cycle and have far-reaching effects on mood, cognition, and pain threshold — they modulate neurotransmitter systems throughout the brain, not just reproduction.</p>
              <p>The appetite hormones (ghrelin, leptin, insulin) form a feedback system for energy regulation: ghrelin signals hunger, leptin signals satiety from fat stores, insulin shuttles glucose into cells. All three are disrupted by sleep deprivation and chronic stress — a major reason why stress and poor sleep tend to cause weight gain.</p>
              <p>Vasopressin, prolactin, growth hormone, and DHEA round out the picture: water balance, post-intimacy bonding and refractory state, physical repair during sleep, and stress resilience.</p>
            </div>
          </div>
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="estradiol"    label="Estradiol"    value={ne.estradiol    ?? 100} unit="pg/mL" normalized={norm('estradiol',    ne.estradiol    ?? 100)} tooltip="Estradiol — Primary Estrogen\n\nThe main estrogen in women of reproductive age. Drives the monthly cycle and supports bone density, cardiovascular health, cognitive function, mood stability, and skin elasticity.\n\nFluctuates through cycle: low during menstruation, rises through follicular phase, peaks at ovulation (~200–400 pg/mL), drops in luteal phase.\nLow (as in menopause or hypothalamic amenorrhea): hot flashes, poor sleep, cognitive fog, low drive, mood instability, bone loss.\n\nKey interactions: Estradiol boosts serotonin, dopamine, and acetylcholine signaling. The drop before a period explains mood vulnerability that week. It also has anti-inflammatory effects." />
            <ChemicalReadOnly field="progesterone" label="Progesterone" value={ne.progesterone ?? 0.5} unit="ng/mL" normalized={norm('progesterone', ne.progesterone ?? 0.5)} tooltip="Progesterone — The Luteal Calm (and PMDD Culprit)\n\nReleased by the corpus luteum after ovulation, progesterone prepares the uterus for potential pregnancy and is the dominant hormone in the second half of the cycle.\n\nNormal (luteal phase, 5–20 ng/mL): calming, sleep-promoting. Converted to allopregnanolone, which activates GABA-A receptors the same way anti-anxiety drugs do.\nLow in luteal phase: anxiety, insomnia, irritability — the PMDD-vulnerable window.\nVery high: sedating, brain fog, some women describe feeling 'underwater.'\n\nKey interactions: The sharp drop in both estradiol and progesterone just before menstruation triggers PMDD in sensitive individuals. Some synthetic progestins in hormonal contraceptives don't convert to allopregnanolone and can worsen mood." />
            <ChemicalReadOnly field="testosterone" label="Testosterone" value={ne.testosterone ?? 40}  unit="ng/dL" normalized={norm('testosterone', ne.testosterone ?? 40)}  tooltip="Testosterone — Drive, Confidence, and Drive\n\nPresent at much lower levels in women than men, but still critical. Controls drive, assertiveness, competitive drive, spatial cognition, and muscle maintenance.\n\nNormal in women (15–70 ng/dL): healthy drive, energy, and drive.\nHigh: more assertive and competitive, acne.\nLow: low drive, fatigue, loss of motivation and muscle tone. Often suppressed by oral contraceptives (which suppress ovarian androgen production).\n\nKey interactions: Testosterone and estradiol are chemically interconverted. Stress and high cortisol suppress testosterone. Resistance training acutely raises it." />
            <div class="flex items-center gap-2 py-1">
              <span class="text-xs opacity-50">Cycle Day:</span>
              <span class="font-mono text-sm">{(data.cycle_day ?? 0) + 1} / 28</span>
              <span class="badge badge-xs badge-neutral">{cyclePhaseLabel(data.cycle_day ?? 0)}</span>
            </div>
            <div class="divider my-1"></div>
            <ChemicalReadOnly field="ghrelin"        label="Ghrelin"        value={ne.ghrelin        ?? 400} unit="pg/mL" normalized={norm('ghrelin',        ne.ghrelin        ?? 400)} tooltip="Ghrelin — The Hunger Signal\n\nProduced mainly in the stomach, ghrelin rises before meals and falls after eating. The most potent known appetite-stimulating hormone.\n\nNormal: rises predictably before scheduled mealtimes, falls sharply after eating.\nHigh: strong hunger, preoccupation with food, reduced impulse control around eating.\n\nKey interactions: Sleep deprivation sharply raises ghrelin (you eat more the day after a bad night). Stress raises it too. Ghrelin directly stimulates dopamine reward circuits — food becomes more rewarding when you're hungry, which is why willpower-based dieting under stress tends to fail." />
            <ChemicalReadOnly field="leptin"         label="Leptin"         value={ne.leptin         ?? 15}  unit="ng/mL" normalized={norm('leptin',         ne.leptin         ?? 15)}  tooltip="Leptin — The Satiety Signal from Fat\n\nProduced by fat cells, leptin tells the brain how much stored energy is available. High leptin should suppress appetite. Low leptin triggers aggressive hunger.\n\nHigh: should suppress appetite — but obesity involves leptin resistance, where the brain stops hearing the signal despite high levels (similar to insulin resistance).\nLow: extreme hunger, metabolic slowdown — the state of starvation or crash dieting.\n\nKey interactions: Leptin and ghrelin are antagonists. Sleep deprivation lowers leptin and raises ghrelin simultaneously — a double hunger signal. Low leptin suppresses menstruation in athletes and people with very low body fat." />
            <ChemicalReadOnly field="insulin"        label="Insulin"        value={ne.insulin        ?? 5}   unit="µU/mL" normalized={norm('insulin',        ne.insulin        ?? 5)}   tooltip="Insulin — The Glucose Gatekeeper\n\nReleased by the pancreas in response to rising blood sugar, insulin signals cells to absorb glucose from the blood. Without it (Type 1 diabetes), blood sugar climbs dangerously.\n\nNormal fasting (2–10 µU/mL): minimal needed to maintain glucose.\nChronically high (insulin resistance): cells stop responding — the pancreas compensates with more and more insulin, eventually leading to Type 2 diabetes.\n\nKey interactions: High cortisol promotes insulin resistance. Fructose (especially from high-fructose corn syrup) doesn't trigger the same insulin response as glucose, bypassing some satiety signals. The brain itself is not dependent on insulin for glucose uptake — but it is affected downstream." />
            <div class="divider my-1"></div>
            <ChemicalReadOnly field="vasopressin"    label="Vasopressin"    value={ne.vasopressin    ?? 2}   unit="pg/mL" normalized={norm('vasopressin',    ne.vasopressin    ?? 2)}   tooltip="Vasopressin (ADH) — Water Retention and Social Memory\n\nVasopressin has two roles: physically, it tells the kidneys to retain water. Socially, it plays a role in pair bonding, territorial behavior, and social memory (recognizing familiar faces).\n\nNormal (1–3 pg/mL): hydration well-regulated, social recognition intact.\nHigh: water retention, lower urine output, social bonding reinforced.\nLow: excessive urination (diabetes insipidus at extremes), dehydration risk.\n\nKey interactions: Alcohol strongly suppresses vasopressin — why you urinate frequently when drinking and wake up dehydrated. Works alongside oxytocin in bonding; they're often released together during sex and pair bonding." />
            <ChemicalReadOnly field="prolactin"      label="Prolactin"      value={ne.prolactin      ?? 8}   unit="ng/mL" normalized={norm('prolactin',      ne.prolactin      ?? 8)}   tooltip="Prolactin — Post-Reward Refractory and Bonding\n\nBest known for triggering milk production after childbirth. It also rises sharply after peak resolution (contributing to the close personal sleepy, satisfied feeling), after intense stress, and during bonding.\n\nNormal: low except postpartum, after peak resolution, or during stress.\nElevated: intimate refractory period, calming, sometimes fatigue.\nChronically high (hyperprolactinemia): suppresses sex hormones — low drive, irregular periods, potential infertility.\n\nKey interactions: Dopamine suppresses prolactin. Dopamine-blocking antipsychotics often cause hyperprolactinemia as a side effect. Prolactin peaks during REM sleep." />
            <ChemicalReadOnly field="growth_hormone" label="Growth Hormone" value={ne.growth_hormone ?? 1}   unit="ng/mL" normalized={norm('growth_hormone', ne.growth_hormone ?? 1)}   tooltip="Growth Hormone (GH) — Repair and Anabolism\n\nGH is released in pulses, with the largest surge in the first hours of deep sleep. It drives tissue repair, muscle protein synthesis, fat mobilization, and bone density.\n\nNormal (pulsatile): adequate GH contributes to physical recovery from exercise, morning alertness, and body composition.\nLow: poor recovery, muscle loss, increased fat mass, fatigue. Creates a negative feedback loop: poor sleep reduces GH, which worsens recovery, which worsens sleep quality.\n\nKey interactions: Even one bad night dramatically reduces the nightly GH pulse — a key mechanism by which sleep deprivation impairs physical performance. Cortisol antagonizes GH." />
            <ChemicalReadOnly field="dhea"           label="DHEA"           value={ne.dhea           ?? 150} unit="µg/dL" normalized={norm('dhea',           ne.dhea           ?? 150)} tooltip="DHEA — Anti-Stress Buffer\n\nProduced by the adrenal glands, DHEA is a precursor for both estrogens and testosterone. It also directly counteracts many of cortisol's harmful effects.\n\nNormal (150–300 µg/dL in young adults): acts as a natural resilience factor. Declines steadily with age.\nHigh: energy, drive, well-being.\nLow: fatigue, stress intolerance, increased susceptibility to cortisol damage.\n\nKey interactions: The cortisol-to-DHEA ratio is a useful marker of chronic stress — as cortisol climbs and DHEA depletes, resilience erodes. DHEA supplements are sold OTC in the US, though evidence is mixed." />
          </div>
        </TierCard>
        </div>
      </div>

    <!-- ═══════════════════════════════ IMMUNE / PAIN ═════════════════════════ -->
    {:else if activeTab === 'immune'}
      {@const im = data.immune ?? {}}
      {@const pa = data.pain  ?? {}}
      <div class="flex flex-col gap-4">
        <TierCard title="Immune">
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What are Cytokines?</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>Cytokines are chemical messengers released by immune cells. When the body detects infection, injury, or threat, cytokines coordinate the response: calling more immune cells to the area, raising body temperature (fever), and triggering "sickness behavior" — the complex of fatigue, loss of appetite, social withdrawal, and heightened pain sensitivity that makes you want to rest and recover.</p>
              <p>This is not malfunction. Sickness behavior is adaptive: it conserves energy for fighting the infection and keeps you from spreading it. The problem arises when cytokines stay elevated chronically — which can happen under ongoing psychological stress — producing a low-grade inflammatory state linked to depression, cardiovascular disease, and cognitive decline.</p>
              <p>IL-1β, IL-6, and TNF-α are pro-inflammatory. IL-10 is the anti-inflammatory brake. CRP is a downstream marker produced by the liver in response to IL-6 — it's the most common inflammation blood test.</p>
            </div>
          </div>
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="il1b"      label="IL-1β"              value={im.il1b      ?? 2}   unit="pg/mL" normalized={norm('il1b',     im.il1b     ?? 2)}   tooltip="IL-1β — The Sickness Trigger\n\nInterleukin-1 beta is a pro-inflammatory cytokine released by immune cells when they detect infection or tissue damage. Its job is to orchestrate sickness behavior.\n\nNormal (<5 pg/mL): baseline immune surveillance.\nElevated: fatigue, fever, loss of appetite, social withdrawal, hypersensitivity to pain. Your body is telling you to rest while it fights.\nVery high (>20): full sickness cascade active.\n\nKey interactions: IL-1β strongly suppresses dopamine signaling — why illness kills motivation and mood. It raises prostaglandin E2 (the fever generator). NSAIDs (ibuprofen, aspirin) block prostaglandin production downstream of IL-1β." />
            <ChemicalReadOnly field="il6"       label="IL-6"               value={im.il6       ?? 3}   unit="pg/mL" normalized={norm('il6',      im.il6      ?? 3)}   tooltip="IL-6 — Acute Phase Commander\n\nA cytokine that rises quickly during infection, injury, or intense exercise. Tells the liver to produce acute phase proteins (like CRP) and drives the systemic inflammatory response.\n\nNormal (<7 pg/mL): low-level immune regulation.\nElevated: signals active infection, injury, or intense physical stress.\n\nKey interactions: Exercise acutely raises IL-6 from muscle tissue as part of a healthy response — distinct from the inflammatory IL-6 of infection. Chronic low-grade IL-6 elevation is associated with depression. Anti-IL-6 biologics (tocilizumab) are used in severe autoimmune disease and severe COVID-19." />
            <ChemicalReadOnly field="tnf_alpha" label="TNF-α"              value={im.tnf_alpha ?? 3}   unit="pg/mL" normalized={norm('tnf_alpha', im.tnf_alpha ?? 3)}  tooltip="TNF-α — Systemic Inflammation Coordinator\n\nTumor Necrosis Factor-alpha coordinates broad inflammatory responses — activating other immune cells, increasing vascular permeability, inducing fever, and triggering sickness behavior including social withdrawal.\n\nNormal (<8 pg/mL): immune surveillance.\nElevated: drives fatigue, pain sensitization, and depressive-like symptoms. Chronically elevated in autoimmune conditions like rheumatoid arthritis.\n\nKey interactions: TNF-α directly impairs serotonin metabolism, contributing to the depression seen in chronic inflammatory disease. Anti-TNF biologics (Humira, Enbrel) are used in autoimmune conditions and sometimes improve depressive symptoms as a side effect." />
            <ChemicalReadOnly field="crp"       label="C-Reactive Protein" value={im.crp       ?? 0.5} unit="mg/L"  normalized={norm('crp',      im.crp      ?? 0.5)} tooltip="CRP — Inflammation Meter\n\nC-Reactive Protein is produced by the liver in response to IL-6. It's a non-specific marker — it doesn't tell you what's causing inflammation, just that some is present.\n\nNormal (<1.0 mg/L): low baseline.\nMild elevation (1–3 mg/L): low-grade chronic inflammation — associated with cardiovascular risk.\nHigh (>10 mg/L): active infection, tissue injury, or acute autoimmune flare.\n\nKey interactions: CRP can remain elevated for days to weeks after an acute illness. Statins lower CRP independent of cholesterol — some cardiovascular benefit may be anti-inflammatory." />
            <ChemicalReadOnly field="il10"      label="IL-10"              value={im.il10      ?? 10}  unit="pg/mL" normalized={norm('il10',     im.il10     ?? 10)}  tooltip="IL-10 — The Off Switch\n\nInterleukin-10 is the primary anti-inflammatory cytokine. Its job is to slow down and terminate the inflammatory response once the threat is resolved, preventing collateral damage to healthy tissue.\n\nNormal (5–20 pg/mL): keeping inflammation in check.\nHigh: suppressing acute inflammation — normal after the peak of an immune response.\nLow: inadequate braking, contributing to chronic inflammatory conditions.\n\nKey interactions: The balance between pro-inflammatory cytokines (IL-1β, IL-6, TNF-α) and IL-10 determines whether inflammation resolves cleanly or persists. Some pathogens hijack IL-10 signaling to evade immune clearance." />

            <div class="mt-1">
              <div class="flex justify-between items-center mb-1">
                <span class="text-sm">Inflammation Index</span>
                <span class="badge badge-xs {labelBadge('inflammation_index', im.inflammation_index ?? 0)}">{labelName('inflammation_index', im.inflammation_index ?? 0)}</span>
              </div>
              <progress class="progress w-full {labelBar('inflammation_index', im.inflammation_index ?? 0)}" value={im.inflammation_index ?? 0} max="1"></progress>
            </div>

            {#if (im.il1b ?? 0) > 20}
              <div class="alert alert-warning py-2">
                <span class="text-xs">SICKNESS CASCADE ACTIVE — elevated IL-1β triggering withdrawal and fatigue</span>
              </div>
            {/if}
          </div>
        </TierCard>

        <TierCard title="Pain &amp; Autonomic">
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">Pain Signaling and Central Sensitization</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>Pain is not simply a signal from damaged tissue — it's a construction by the nervous system. The same tissue injury produces very different pain experiences depending on context, mood, stress, and pain history.</p>
              <p>Substance P carries nociceptive (pain) signals from the periphery to the spinal cord. Prostaglandin E2 sensitizes receptors, lowering the threshold for what counts as painful — why a minor cut hurts more during a fever.</p>
              <p>Central sensitization is when the amplification system itself gets stuck "on" even after the original injury heals. The spinal cord and brain become hyperresponsive to all signals — the mechanism behind chronic pain conditions like fibromyalgia. Vagal tone reflects how well the parasympathetic (rest-and-digest) system is counterbalancing the sympathetic stress response.</p>
            </div>
          </div>
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="substance_p" label="Substance P"      value={pa.substance_p ?? 30} unit="pg/mL" normalized={norm('substance_p', pa.substance_p ?? 30)} tooltip="Substance P — Pain Amplifier\n\nA neuropeptide that carries pain signals from the site of injury to the spinal cord and brain. It doesn't create pain — it amplifies and broadcasts it.\n\nNormal (10–50 pg/mL): low, carrying minor background tissue signals.\nElevated: pain signals louder — from actual injury and in central sensitization where amplification gets stuck on.\n\nKey interactions: Substance P is elevated in fibromyalgia, IBS, and PTSD — conditions involving central sensitization without ongoing tissue damage. Capsaicin (chili peppers) initially activates then depletes Substance P from local nerve endings, which is why capsaicin creams relieve pain after an initial burning phase." />
            <ChemicalReadOnly field="pge2"        label="Prostaglandin E2" value={pa.pge2        ?? 80} unit="pg/mL" normalized={norm('pge2',        pa.pge2        ?? 80)} tooltip="Prostaglandin E2 — The Pain and Fever Generator\n\nPGE2 is produced from arachidonic acid (in cell membranes) during inflammation. It sensitizes pain receptors to become more responsive — a papercut hurts more during a fever for this reason.\n\nNormal (40–100 pg/mL): minimal sensitization.\nElevated: pain threshold lowered, fever maintained, blood vessels dilated.\n\nKey interactions: NSAIDs (ibuprofen, aspirin, naproxen) block COX enzymes that produce PGE2 — this is their primary mechanism for reducing pain, fever, and inflammation. Paracetamol (acetaminophen) reduces PGE2 centrally but not peripherally, which is why it reduces pain without much anti-inflammatory effect." />

            <div>
              <div class="flex justify-between items-center mb-1">
                <span class="text-sm">Pain Intensity</span>
                <div class="flex items-center gap-2">
                  <span class="badge badge-xs {labelBadge('pain_intensity', pa.pain_intensity ?? 0)}">{labelName('pain_intensity', pa.pain_intensity ?? 0)}</span>
                  <span class="text-xs font-mono opacity-50">{((pa.pain_intensity ?? 0) * 100).toFixed(0)}/100</span>
                </div>
              </div>
              <progress class="progress w-full {labelBar('pain_intensity', pa.pain_intensity ?? 0)}" value={pa.pain_intensity ?? 0} max="1"></progress>
            </div>

            <div>
              <div class="flex justify-between items-center mb-1">
                <span class="text-sm">Central Sensitization</span>
                <span class="badge badge-xs {labelBadge('central_sensitization', pa.central_sensitization ?? 0)}">{labelName('central_sensitization', pa.central_sensitization ?? 0)}</span>
              </div>
              <progress class="progress w-full {labelBar('central_sensitization', pa.central_sensitization ?? 0)}" value={pa.central_sensitization ?? 0} max="1"></progress>
            </div>

            <div>
              <div class="flex justify-between items-center mb-1">
                <div class="tooltip tooltip-bottom text-left cursor-help">
                  <span class="text-sm">Vagal Tone</span>
                  <div class="tooltip-content text-left text-xs leading-relaxed" style="max-width: 20rem; white-space: normal;"><strong>Vagal Tone — Parasympathetic Balance</strong><br><br>A measure of how active the vagus nerve is — the main nerve of the parasympathetic (rest-and-digest) nervous system. Higher vagal tone = better ability to calm down after stress.<br><br><strong>Normal (0.5–0.7):</strong> good autonomic balance, resilient stress response.<br><strong>High:</strong> excellent recovery, heart rate variability, emotional regulation.<br><strong>Low:</strong> poor stress recovery, tendency to stay stuck in fight-or-flight.<br><br><strong>Key interactions:</strong> Improved by deep slow breathing, cold exposure, exercise, and social connection. Low vagal tone is associated with anxiety, depression, and inflammatory conditions.</div>
                </div>
                <span class="badge badge-xs {labelBadge('vagal_tone', pa.vagal_tone ?? 0.55)}">{labelName('vagal_tone', pa.vagal_tone ?? 0.55)}</span>
              </div>
              <progress class="progress w-full {labelBar('vagal_tone', pa.vagal_tone ?? 0.55)}" value={pa.vagal_tone ?? 0.55} max="1"></progress>
            </div>
          </div>
        </TierCard>
      </div>

    <!-- ═══════════════════════════════ CIRCADIAN ══════════════════════════════ -->
    {:else if activeTab === 'circadian'}
      {@const b    = data.body ?? {}}
      {@const ne   = data.neuroendocrine ?? {}}
      {@const mel  = data.chemicals['melatonin']?.value ?? 5}
      {@const adeno = b.adenosine ?? 38}
      {@const orexin = ne.orexin ?? 300}
      {@const phase  = b.circadian_phase ?? 0}
      {@const temp   = b.core_temp ?? 37}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Two-Process Sleep Model</h2>
            <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
              <input type="checkbox" />
              <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">How Sleep Pressure Works — Two Processes</div>
              <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
                <p>Sleep is controlled by two independent systems that interact. <strong>Process S</strong> (homeostatic) is adenosine — a waste product that builds up while you're awake and clears during sleep. The longer you stay awake, the higher it climbs, and the stronger the pull toward sleep.</p>
                <p><strong>Process C</strong> (circadian) is the internal clock — your body's 24-hour rhythm that signals when it is biologically night. This is melatonin (darkness signal) and orexin (wakefulness drive). Even if you haven't slept, the circadian system will push you alert in the morning and sleepy at night.</p>
                <p>Sleep happens when both processes align: adenosine is high (you're tired) and the circadian system is in its night window. Caffeine only helps with adenosine — it doesn't reset the circadian signal, which is why it keeps you awake past your normal time but leaves you groggy when morning comes regardless.</p>
              </div>
            </div>
            <p class="text-xs opacity-50 mb-1">Process S — Adenosine (Homeostatic Drive)</p>
            <ChemicalReadOnly field="adenosine" label="Adenosine" value={adeno} unit="nM" normalized={norm('adenosine', adeno)} tooltip="Adenosine — Sleep Pressure (Process S)\n\nA waste product neurons produce while active. It builds up the entire time you are awake and clears during sleep — this is the physical substrate of feeling tired.\n\nNormal (25–55 nM): alert, no urgency.\nHigh (70+): heavy-headed, hard to concentrate, craving sleep.\nVery high (85+): near-involuntary sleep onset — microsleeps become likely.\n\nKey interaction: Caffeine blocks adenosine receptors (it does not reduce adenosine, it just hides the signal). When caffeine wears off, the accumulated adenosine floods back all at once — the 'caffeine crash.'" />
            <div class="flex justify-between text-xs opacity-30 mt-1 mb-4">
              <span>15 rested</span><span>60 tired</span><span>80 onset</span><span>92 critical</span>
            </div>
            <p class="text-xs opacity-50 mb-1">Process C — Circadian Drive</p>
            <div class="flex flex-col gap-3">
              <ChemicalReadOnly field="melatonin" label="Melatonin" value={mel}    unit="pg/mL" normalized={norm('melatonin', mel)}    tooltip="Melatonin — Darkness Signal (Process C)\n\nProduced by the pineal gland when it gets dark. Melatonin does not cause sleep — it signals the body that it is nighttime, shifting the body into sleep-preparedness mode.\n\nNormal nighttime peak (100–200 pg/mL): timing the transition to sleep. Natural levels are far lower than most OTC supplements.\nSuppressed (by light exposure): blue light at night prevents melatonin production, delaying sleep onset — the mechanism behind the phone-in-bed problem.\n\nKey interactions: Melatonin and adenosine work together but through different mechanisms. Adenosine = how long you've been awake (homeostatic). Melatonin = what time it is (circadian). Both must be permissive for sleep to occur." dimmed={true} />
              <ChemicalReadOnly field="orexin"    label="Orexin"    value={orexin} unit="pg/mL" normalized={norm('orexin',    orexin)} tooltip="Orexin (Hypocretin) — The Wakefulness Anchor\n\nOrexin neurons in the lateral hypothalamus fire to actively maintain wakefulness. They suppress the sleep-switch. When these neurons are destroyed (as in narcolepsy), people involuntarily fall asleep mid-activity.\n\nNormal (200–400 pg/mL): awake and able to sustain alertness.\nHigh: strong wakefulness, difficulty falling asleep.\nLow: sleep attacks, sudden muscle weakness triggered by emotion (cataplexy in narcolepsy).\n\nKey interactions: Orexin is suppressed by rising adenosine — as sleep pressure builds, the wakefulness drive weakens. New sleeping pills (suvorexant/lemborexant) work by blocking orexin receptors rather than sedating the whole brain with GABA agonists." />
            </div>
            <div class="mt-4 p-3 rounded bg-base-300">
              <div class="flex justify-between items-center">
                <span class="text-sm">Sleep Homeostasis</span>
                <span class="badge badge-sm badge-neutral">{sleepLabel(adeno, mel)}</span>
              </div>
            </div>
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Core Temperature</h2>
            <div class="flex items-center justify-between mb-2">
              <span class="text-2xl font-mono font-bold {labelText('core_temp', temp)}">{temp.toFixed(2)} °C</span>
              <span class="badge {labelBadge('core_temp', temp)}">{labelName('core_temp', temp)}</span>
            </div>
            <progress class="progress w-full {labelBar('core_temp', temp)}" value={norm('core_temp', temp)} max="1"></progress>
            <p class="text-xs opacity-40 mt-3 leading-relaxed">Core temperature follows the circadian cycle — it dips to its lowest ~2 hours before habitual wake time, which is when sleep pressure is highest. Rising core temp in the evening delays sleep onset; warm baths work paradoxically because they dump heat from the skin, causing a rebound drop.</p>
          </div>
        </div>

        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Circadian Phase</h2>
            <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
              <input type="checkbox" />
              <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What is Circadian Phase?</div>
              <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
                <p>Your body runs on a roughly 24-hour internal clock driven by a cluster of neurons in the hypothalamus called the SCN (suprachiasmatic nucleus). This clock regulates body temperature, hormone release timing, digestive readiness, immune function, and cognitive performance — all of which peak and trough at different phases.</p>
                <p>The clock is reset daily by light exposure — particularly short-wavelength (blue) light in the morning advances the clock toward earlier wake times, while evening light delays it. Meals and exercise also have smaller synchronizing effects.</p>
                <p>Phase here is expressed as a fraction of the 24-hour cycle (0.0 = midnight, 0.5 = noon). Jet lag and shift work are acute examples of behavior being out of phase with the body clock — not just tiredness, but impaired immune function, mood disruption, and metabolic dysfunction.</p>
              </div>
            </div>
            <!-- CSS circular clock -->
            <div class="flex justify-center mb-4">
              <div class="relative w-40 h-40">
                <div class="absolute inset-0 rounded-full border-4 border-base-300"></div>
                <div class="absolute top-1 left-1/2 -translate-x-1/2 text-xs opacity-30">12</div>
                <div class="absolute bottom-1 left-1/2 -translate-x-1/2 text-xs opacity-30">0</div>
                <div class="absolute left-1 top-1/2 -translate-y-1/2 text-xs opacity-30">18</div>
                <div class="absolute right-1 top-1/2 -translate-y-1/2 text-xs opacity-30">6</div>
                <div
                  class="absolute w-4 h-4 rounded-full bg-primary shadow-lg"
                  style="top:50%;left:50%;transform-origin:0 0;transform:rotate({phase * 360}deg) translateY(-55px) translate(-50%,-50%)"
                ></div>
                <div class="absolute inset-0 flex items-center justify-center">
                  <span class="text-sm font-mono opacity-60">{(phase * 24).toFixed(1)}h</span>
                </div>
              </div>
            </div>
            <div class="flex justify-between items-center">
              <span class="text-sm opacity-60">Phase {phase.toFixed(3)}</span>
              <span class="badge badge-sm {labelBadge('circadian_phase', phase)}">{labelName('circadian_phase', phase)}</span>
            </div>
            <progress class="progress progress-primary w-full mt-2" value={phase} max="1"></progress>
          </div>
        </div>
      </div>

    <!-- ═══════════════════════════════ PLASTICITY ═════════════════════════════ -->
    {:else if activeTab === 'plasticity'}
      {@const np = data.neuroplasticity ?? {}}
      {@const al = data.allostatic_load ?? 0}
      {@const bdnf = np.bdnf ?? 9}
      {@const sp01 = np.synaptic_potentiation ?? 0.5}
      <div class="flex flex-col gap-4">
        <TierCard title="Neuroplasticity">
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What is Neuroplasticity?</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>Neuroplasticity is the brain's ability to change its own structure and function in response to experience. It's how you learn, recover from injury, and adapt to new environments. The old idea that the adult brain is fixed and static is wrong — synaptic connections are constantly being strengthened, weakened, pruned, and sometimes created throughout life.</p>
              <p>BDNF (brain-derived neurotrophic factor) is the key molecular signal for this change — it supports neuron survival and growth, facilitates synapse formation, and is essential for memory consolidation. Synaptic potentiation reflects whether connections are currently being strengthened (LTP) or weakened (LTD). Both are necessary: LTP is learning; LTD is forgetting the unimportant.</p>
              <p>The brain prunes during sleep, consolidates during deep sleep, and restores BDNF levels overnight. Chronic stress, poor sleep, and high cortisol all suppress plasticity — the brain becomes more rigid when it's under sustained threat.</p>
            </div>
          </div>
          <div class="flex flex-col gap-4">
            <div>
              <div class="flex justify-between items-center mb-1">
                <div class="tooltip tooltip-bottom text-left">
                  <span class="text-sm cursor-help">BDNF</span>
                  <div class="tooltip-content text-left text-xs leading-relaxed" style="max-width: 20rem; white-space: normal;"><strong>BDNF — Brain Fertilizer</strong><br><br>A protein that promotes the growth, maintenance, and survival of neurons. Essential for learning and memory, and one of the key mechanisms by which exercise improves mood and cognition.<br><br><strong>Normal (8–12 ng/mL):</strong> healthy synaptic plasticity, good capacity for learning.<br><strong>High:</strong> actively building new connections — after exercise, learning, or antidepressant treatment.<br><strong>Low:</strong> impaired memory consolidation, reduced neuroplasticity, associated with depression and neurodegenerative risk.<br><br><strong>Key interactions:</strong> Exercise is the most powerful known BDNF stimulant. SSRIs increase BDNF — this may be part of how they treat depression. Chronic stress and high cortisol suppress it. Sleep is critical for BDNF-mediated consolidation of daily learning.</div>
                </div>
                <div class="flex items-center gap-2">
                  <span class="badge badge-xs {labelBadge('bdnf', bdnf)}">{labelName('bdnf', bdnf)}</span>
                  <span class="text-xs opacity-50">ng/mL</span>
                  <span class="text-sm font-mono w-14 text-right">{bdnf.toFixed(2)}</span>
                </div>
              </div>
              <progress class="progress w-full {labelBar('bdnf', bdnf)}" value={norm('bdnf', bdnf)} max="1"></progress>
            </div>

            <div>
              <div class="flex justify-between items-center mb-1">
                <div class="tooltip tooltip-bottom text-left">
                  <span class="text-sm cursor-help">Synaptic Potentiation</span>
                  <div class="tooltip-content text-left text-xs leading-relaxed" style="max-width: 20rem; white-space: normal;"><strong>Synaptic Potentiation — Connection Strength</strong><br><br>Reflects the LTP/LTD balance — whether synaptic connections are being strengthened (Long-Term Potentiation) or weakened (Long-Term Depression).<br><br>LTP is how learning and memory physically work: repeated activation of a synapse makes it fire more easily next time. LTD is equally important: it prunes unused connections, preventing the brain from filling with noise.<br><br><strong>High (0.7+):</strong> active learning state — new information being encoded into durable connections.<br><strong>Low (below 0.3):</strong> synaptic depression dominant — connections weakening, memory consolidation impaired.<br><br><strong>Key interactions:</strong> NMDA glutamate receptors are the "coincidence detectors" that trigger LTP. Ketamine and alcohol both block NMDA receptors. Deep sleep consolidates the day's LTP into permanent memory.</div>
                </div>
                <div class="flex items-center gap-2">
                  <span class="badge badge-xs {labelBadge('synaptic_potentiation', sp01)}">{labelName('synaptic_potentiation', sp01)}</span>
                  <span class="text-sm font-mono">{(sp01 * 100).toFixed(0)}/100</span>
                </div>
              </div>
              <progress class="progress w-full {labelBar('synaptic_potentiation', sp01)}" value={sp01} max="1"></progress>
            </div>
          </div>
        </TierCard>

        <TierCard title="Allostatic Load">
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What is Allostatic Load?</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>Allostasis is the process of maintaining stability through change — your body constantly adjusting to keep you functioning as conditions shift. Allostatic load is the cumulative wear and tear from doing this over and over, especially when demands exceed recovery.</p>
              <p>Think of it as money in a resilience account. Each stressor — physical, emotional, social, immunological — makes a withdrawal. Sleep, good nutrition, exercise, and social connection make deposits. When the account runs low, small stressors that would normally be absorbed become overwhelming.</p>
              <p>High allostatic load does not mean you are weak — it means you have been carrying a lot for a long time. The effects are measurable: elevated inflammatory markers, dysregulated cortisol, impaired sleep architecture, reduced cognitive flexibility, and a lower threshold for emotional reactivity.</p>
            </div>
          </div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-lg font-mono font-bold {labelText('allostatic_load', al)}">{(al * 100).toFixed(1)}</span>
            <div class="flex items-center gap-2">
              <span class="badge {labelBadge('allostatic_load', al)}">{labelName('allostatic_load', al)}</span>
              <span class="text-xs opacity-40">/ 100</span>
            </div>
          </div>
          <div class="relative">
            <progress class="progress w-full {alColor(al)}" value={al} max="1"></progress>
            <div class="absolute top-0 h-full" style="left:30%"><div class="w-px h-full bg-base-content opacity-20"></div></div>
            <div class="absolute top-0 h-full" style="left:60%"><div class="w-px h-full bg-base-content opacity-20"></div></div>
            <div class="absolute top-0 h-full" style="left:85%"><div class="w-px h-full bg-base-content opacity-30"></div></div>
          </div>
          <div class="flex justify-between text-xs opacity-30 mt-1">
            <span>resilient</span><span>moderate</span><span>high</span><span>critical</span>
          </div>
          {#if getLabel('allostatic_load', al)}
            {@const ale = getLabel('allostatic_load', al)}
            <p class="text-xs opacity-50 mt-3 italic">{ale?.implication}</p>
          {/if}
        </TierCard>

        {#if Object.keys(data.personality_drift ?? {}).length > 0}
          <TierCard title="Personality Drift" defaultOpen={false}>
            <p class="text-xs opacity-40 mb-3">Big Five trait modifiers from allostatic load. Delta from baseline.</p>
            <div class="grid grid-cols-2 gap-2">
              {#each Object.entries(data.personality_drift ?? {}) as [trait, delta]}
                <div class="flex items-center justify-between px-2 py-1 rounded bg-base-300">
                  <span class="text-xs opacity-60 capitalize">{trait}</span>
                  <span class="font-mono text-xs {delta > 0 ? 'text-success' : delta < 0 ? 'text-error' : 'opacity-40'}">{delta > 0 ? '+' : ''}{(delta * 100).toFixed(1)}%</span>
                </div>
              {/each}
            </div>
          </TierCard>
        {/if}

        <TierCard title="Receptor Sensitivity" defaultOpen={false}>
          <div class="collapse collapse-arrow bg-base-300 rounded-box mb-4">
            <input type="checkbox" />
            <div class="collapse-title text-xs font-semibold opacity-50 uppercase tracking-wider min-h-0 py-2 px-3">What is Receptor Sensitivity?</div>
            <div class="collapse-content text-xs leading-relaxed opacity-70 space-y-2">
              <p>Receptors are the "docking ports" on neurons where neurotransmitters attach to trigger an effect. Receptor sensitivity measures how responsive those ports currently are — 1.00 is the baseline normal. Above 1.00 (upregulated) means the neuron has become more sensitive; below 1.00 (downregulated) means it has become less sensitive.</p>
              <p>These changes happen gradually in response to chronic over- or under-exposure to a chemical. The brain adapts: if a receptor is constantly flooded, it pulls some ports off the surface (downregulation, building tolerance). If a receptor is chronically understimulated, it adds more ports (upregulation, hypersensitivity). This is the physical mechanism behind drug tolerance, withdrawal, and why stopping a medication abruptly can cause rebound effects.</p>
              <p>Hover each receptor label for a plain-English explanation of what it does.</p>
            </div>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {#each RECEPTOR_FIELDS as r}
              {@const val = data.receptor_sensitivity?.[r.key] ?? 1.0}
              {@const rl = receptorLabel(val)}
              <div class="flex items-center justify-between px-2 py-1 rounded bg-base-300">
                <div class="tooltip tooltip-bottom text-left">
                  <span class="text-xs font-mono opacity-70 cursor-help">{r.name}</span>
                  <div class="tooltip-content text-left text-xs leading-relaxed" style="max-width: 18rem; white-space: normal;">{@html RECEPTOR_TOOLTIPS[r.key] ?? r.name}</div>
                </div>
                <div class="flex items-center gap-1">
                  <span class="badge badge-xs {rl.color}">{rl.name}</span>
                  <span class="text-xs font-mono opacity-50">{val.toFixed(2)}</span>
                </div>
              </div>
            {/each}
          </div>
        </TierCard>
      </div>
    {/if}

    <!-- ════════════════════════════════ HISTORY ════════════════════════════ -->
    {#if activeTab === 'history'}
      <div class="flex flex-col gap-6">

        <!-- Controls -->
        <div class="flex items-center gap-4 flex-wrap">
          <span class="text-sm opacity-60">Time window:</span>
          {#each [1, 3, 6, 12, 24] as w}
            <button
              class="btn btn-xs {historyWindow === w ? 'btn-primary' : 'btn-ghost'}"
              onclick={() => historyWindow = w}
            >{w}h</button>
          {/each}
          {#if historyLoading}
            <span class="loading loading-spinner loading-xs opacity-40"></span>
          {/if}
          {#if historyError}
            <span class="text-xs text-error">{historyError}</span>
          {/if}
          <span class="text-xs opacity-30 ml-auto">{history.length} points</span>
        </div>

        {#if history.length === 0 && !historyLoading}
          <div class="card bg-base-200 px-6 py-10 text-center">
            <p class="opacity-50 text-sm">No history yet. Snapshots are recorded every 10 seconds while the dashboard server is running.</p>
          </div>
        {:else}
          {@const sleepBands = (() => {
            const bands: Array<{start: number; end: number}> = [];
            let sleepStart: number | null = null;
            for (const snap of history) {
              if (snap.sleeping && sleepStart === null) sleepStart = snap.ts;
              if (!snap.sleeping && sleepStart !== null) {
                bands.push({ start: sleepStart, end: snap.ts });
                sleepStart = null;
              }
            }
            if (sleepStart !== null && history.length > 0) {
              bands.push({ start: sleepStart, end: history[history.length - 1].ts });
            }
            return bands;
          })()}

          <!-- Chart tab bar -->
          <div class="tabs tabs-border">
            {#each [
              { id: 'bond',   label: 'Bond & Social'    },
              { id: 'stress', label: 'Stress & Arousal' },
              { id: 'mood',   label: 'Mood & Wellbeing' },
              { id: 'neuro',  label: 'Neuro / Cognition'},
            ] as ct}
              <button
                class="tab {historyChart === ct.id ? 'tab-active font-semibold' : 'opacity-60'}"
                onclick={() => historyChart = ct.id as typeof historyChart}
              >{ct.label}</button>
            {/each}
          </div>

          <!-- Single chart view -->
          <div class="card bg-base-200 p-5">
            {#if historyChart === 'bond'}
              <LineChart
                title="Bond & Social"
                height={500}
                showSleep={true}
                {sleepBands}
                series={[
                  { key: 'oxytocin',     label: 'Oxytocin (pg/mL)',    color: '#f472b6', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.chemicals?.oxytocin     ?? 0 })) },
                  { key: 'dopamine',     label: 'Dopamine (pg/mL)',    color: '#a78bfa', minVal: 0, maxVal: 300, points: history.map(s => ({ ts: s.ts, value: s.chemicals?.dopamine     ?? 0 })) },
                  { key: 'serotonin',    label: 'Serotonin (ng/mL)',   color: '#34d399', minVal: 0, maxVal: 60,  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.serotonin    ?? 0 })) },
                  { key: 'endorphins',   label: 'Endorphins (pg/mL)', color: '#fbbf24', minVal: 0, maxVal: 250, points: history.map(s => ({ ts: s.ts, value: s.chemicals?.endorphins   ?? 0 })) },
                  { key: 'social_warmth',label: 'Social Warmth',       color: '#38bdf8', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.second_order?.social_warmth ?? 0 })) },
                ]}
              />
            {:else if historyChart === 'stress'}
              <LineChart
                title="Stress & Arousal"
                height={500}
                showSleep={true}
                {sleepBands}
                series={[
                  { key: 'cortisol',        label: 'Cortisol (nmol/L)',      color: '#ef4444', minVal: 0, maxVal: 900,  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.cortisol        ?? 0 })) },
                  { key: 'norepinephrine',  label: 'Norepinephrine (pg/mL)', color: '#3b82f6', minVal: 0, maxVal: 2000, points: history.map(s => ({ ts: s.ts, value: s.chemicals?.norepinephrine  ?? 0 })) },
                  { key: 'anxiety',         label: 'Anxiety',                color: '#a855f7', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.third_order?.anxiety         ?? 0 })) },
                  { key: 'arousal',         label: 'Arousal',                color: '#f59e0b', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.second_order?.arousal         ?? 0 })) },
                ]}
              />
            {:else if historyChart === 'mood'}
              <LineChart
                title="Mood & Wellbeing"
                height={500}
                showSleep={true}
                {sleepBands}
                series={[
                  { key: 'mood_valence', label: 'Mood Valence', color: '#60a5fa', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.second_order?.mood_valence ?? 0 })) },
                  { key: 'hedonic_tone', label: 'Hedonic Tone', color: '#f472b6', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.second_order?.hedonic_tone ?? 0 })) },
                  { key: 'energy',       label: 'Energy',       color: '#4ade80', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.second_order?.energy       ?? 0 })) },
                  { key: 'loneliness',   label: 'Loneliness',   color: '#fb923c', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.third_order?.loneliness    ?? 0 })) },
                  { key: 'depression',   label: 'Depression',   color: '#94a3b8', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.third_order?.depression    ?? 0 })) },
                ]}
              />
            {:else if historyChart === 'neuro'}
              <LineChart
                title="Neuro / Cognition"
                height={500}
                showSleep={true}
                {sleepBands}
                series={[
                  { key: 'gaba',              label: 'GABA (μmol/L)',       color: '#22d3ee', minVal: 0, maxVal: 12,  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.gaba              ?? 0 })) },
                  { key: 'glutamate',         label: 'Glutamate (μmol/L)',  color: '#f97316', minVal: 0, maxVal: 16,  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.glutamate         ?? 0 })) },
                  { key: 'acetylcholine',     label: 'Acetylcholine (nM)', color: '#a3e635', minVal: 0, maxVal: 120,  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.acetylcholine     ?? 0 })) },
                  { key: 'cognitive_clarity', label: 'Clarity',             color: '#818cf8', minVal: 0, maxVal: 100, points: history.map(s => ({ ts: s.ts, value: s.second_order?.cognitive_clarity ?? 0 })) },
                ]}
              />
            {/if}
          </div>

          <p class="text-xs opacity-30 text-center">Shaded bands = sleep periods. All series normalized to same 0–1 scale for comparison. Hover for raw values.</p>
        {/if}

      </div>
    {/if}

  {/if}
</div>
