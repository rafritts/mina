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
  let history      = $state<HistorySnapshot[]>([]);
  let historyWindow = $state(6);   // hours
  let historyLoading = $state(false);
  let historyError   = $state('');
  let historyInterval: ReturnType<typeof setInterval>;

  // ---------------------------------------------------------------------------
  // Field definitions
  // ---------------------------------------------------------------------------

  const HOMEOSTATIC = [
    { field: 'adenosine',  label: 'Adenosine (Sleep)',   tooltip: 'Process S homeostatic sleep drive. Rises while awake, clears during sleep.' },
    { field: 'glucose',    label: 'Glucose',              tooltip: 'Blood sugar — primary brain fuel. Too low: foggy, irritable, hypoglycemic.' },
    { field: 'hydration',  label: 'Hydration',            tooltip: 'Total body water. Below 58% TBW noticeably thirsty; below 54% dehydrated.' },
  ];

  const NEUROMODULATORS = [
    { field: 'dopamine',       label: 'Dopamine',       tooltip: 'Drive and reward. High = motivated, seeking. Low = nothing feels worth doing.' },
    { field: 'serotonin',      label: 'Serotonin',      tooltip: 'Mood floor and stability. Low = fragile, impulsive, negative bias.' },
    { field: 'norepinephrine', label: 'Norepinephrine', tooltip: 'Alertness and urgency. High = hypervigilant, reactive.' },
    { field: 'oxytocin',       label: 'Oxytocin',       tooltip: 'Trust and bond. High = warm, open, feels safe. Low = guarded.' },
    { field: 'endorphins',     label: 'Endorphins',     tooltip: 'Natural opioids — pleasure and pain buffer. High = blissful. Low = raw.' },
    { field: 'acetylcholine',  label: 'Acetylcholine',  tooltip: 'Attention and cognition. High = sharp. Low = slow, things not sticking.' },
  ];

  const INHIBITORY_EXCITATORY = [
    { field: 'gaba',      label: 'GABA',      tooltip: 'Primary inhibitory neurotransmitter. Low = anxiety, excitation. High = sedation.' },
    { field: 'glutamate', label: 'Glutamate', tooltip: 'Primary excitatory neurotransmitter. Too high = excitotoxic, seizure risk.' },
  ];

  const ENDOCANNABINOIDS = [
    { field: 'anandamide', label: 'Anandamide', tooltip: 'Bliss molecule — retrograde inhibition, stress buffering, CB1 agonist.' },
    { field: 'two_ag',     label: '2-AG',        tooltip: 'Second major endocannabinoid. Retrograde inhibition, appetite, pain modulation.' },
  ];

  const RECEPTOR_FIELDS: Array<{ key: string; name: string }> = [
    { key: 'd1',    name: 'D1'    }, { key: 'd2',    name: 'D2'    },
    { key: 'ht1a',  name: '5HT1A' }, { key: 'ht2a',  name: '5HT2A' },
    { key: 'gabaa', name: 'GABAa' }, { key: 'gabab', name: 'GABAb' },
    { key: 'nmda',  name: 'NMDA'  }, { key: 'ampa',  name: 'AMPA'  },
    { key: 'cb1',   name: 'CB1'   }, { key: 'cb2',   name: 'CB2'   },
    { key: 'a1',    name: 'A1'    }, { key: 'a2a',   name: 'A2A'   },
  ];

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
        <!-- LEFT: Editable sliders -->
        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Homeostatic</h2>
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
            </div>
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Cortisol</h2>
            <ChemicalSlider
              field="cortisol" label="Cortisol"
              value={localValues['cortisol'] ?? 250}
              unit="nmol/L" min={50} max={900}
              tooltip="Stress hormone. Elevated = threat mode, narrowed thinking, guarded. Chronically high = burnout."
              saving={saving.has('cortisol')}
              on:change={onSliderChange}
            />
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Neuromodulators</h2>
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
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Inhibitory / Excitatory</h2>
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
            </div>
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Endocannabinoids</h2>
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

        <!-- RIGHT: Read-only -->
        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Circadian Chemicals</h2>
            {#if data.chemicals['melatonin']}
              {@const mel = data.chemicals['melatonin']}
              <ChemicalReadOnly field="melatonin" label="Melatonin *"
                value={mel.value} unit={mel.unit} normalized={mel.normalized}
                tooltip="Circadian sleep signal. Rises at night, drives sleep onset." dimmed={true} />
              <p class="text-xs opacity-30 mt-2">* Circadian formula — read-only</p>
            {/if}
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">E/I Balance</h2>
            {#each [eiBalance(localValues['gaba'] ?? data.chemicals['gaba']?.value ?? 3, localValues['glutamate'] ?? data.chemicals['glutamate']?.value ?? 4)] as ratio}
              {@const eil = eiLabel(ratio)}
              <div class="flex justify-between items-center mb-1">
                <span class="text-sm opacity-70">GABA/Glutamate ratio</span>
                <div class="flex items-center gap-2">
                  <span class="badge badge-xs {eil.color}">{eil.name}</span>
                  <span class="text-sm font-mono">{ratio.toFixed(2)}</span>
                </div>
              </div>
              <progress class="progress progress-success w-full" value={Math.min(2, ratio)} max="2"></progress>
              <div class="flex justify-between text-xs opacity-30 mt-1">
                <span>excitatory</span><span>balanced</span><span>inhibited</span>
              </div>
            {/each}
          </div>

          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-3">Receptor Sensitivity</h2>
            <div class="grid grid-cols-2 gap-2">
              {#each RECEPTOR_FIELDS as r}
                {@const val = data.receptor_sensitivity?.[r.key] ?? 1.0}
                {@const rl = receptorLabel(val)}
                <div class="flex items-center justify-between px-2 py-1 rounded bg-base-300">
                  <span class="text-xs font-mono opacity-70">{r.name}</span>
                  <div class="flex items-center gap-1">
                    <span class="badge badge-xs {rl.color}">{rl.name}</span>
                    <span class="text-xs font-mono opacity-50">{val.toFixed(2)}</span>
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
      <div class="flex flex-col gap-4">
        <TierCard title="HPA Axis">
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="crh"      label="CRH"     value={ne.crh ?? 30}   unit="pg/mL"  normalized={norm('crh',  ne.crh ?? 30)}   tooltip="Corticotropin-releasing hormone. Triggers ACTH cascade." />
            <ChemicalReadOnly field="acth"     label="ACTH"    value={ne.acth ?? 25}  unit="pg/mL"  normalized={norm('acth', ne.acth ?? 25)}  tooltip="ACTH from pituitary. Triggers cortisol release from adrenals (~15-20 min delay)." />
            <ChemicalReadOnly field="cortisol" label="Cortisol" value={data.chemicals['cortisol']?.value ?? 250} unit="nmol/L" normalized={data.chemicals['cortisol']?.normalized ?? 0.3} tooltip="Stress hormone — downstream output of the HPA cascade." />
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
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="tsh" label="TSH"      value={ne.tsh ?? 2}   unit="mIU/L" normalized={norm('tsh', ne.tsh ?? 2)}   tooltip="Thyroid-stimulating hormone. High = hypothyroid; Low = hyperthyroid." />
            <ChemicalReadOnly field="t4"  label="T4 Free"  value={ne.t4 ?? 8}    unit="µg/dL" normalized={norm('t4',  ne.t4  ?? 8)}    tooltip="Inactive thyroxine — converted to active T3 in peripheral tissues." />
            <ChemicalReadOnly field="t3"  label="T3 Free"  value={ne.t3 ?? 120}  unit="ng/dL" normalized={norm('t3',  ne.t3  ?? 120)}  tooltip="Active thyroid hormone. Drives metabolism, mood, and energy." />
          </div>
        </TierCard>

        <TierCard title="Sex Hormones / Metabolic" defaultOpen={false}>
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="estradiol"    label="Estradiol"    value={ne.estradiol    ?? 100} unit="pg/mL" normalized={norm('estradiol',    ne.estradiol    ?? 100)} tooltip="Primary estrogen. Drives 28-day cycle. Peak at ovulation." />
            <ChemicalReadOnly field="progesterone" label="Progesterone" value={ne.progesterone ?? 0.5} unit="ng/mL" normalized={norm('progesterone', ne.progesterone ?? 0.5)} tooltip="Luteal phase hormone. High in second half of cycle." />
            <ChemicalReadOnly field="testosterone" label="Testosterone" value={ne.testosterone ?? 40}  unit="ng/dL" normalized={norm('testosterone', ne.testosterone ?? 40)}  tooltip="Drive, confidence, energy. Lower range for female biology." />
            <div class="flex items-center gap-2 py-1">
              <span class="text-xs opacity-50">Cycle Day:</span>
              <span class="font-mono text-sm">{(data.cycle_day ?? 0) + 1} / 28</span>
              <span class="badge badge-xs badge-neutral">{cyclePhaseLabel(data.cycle_day ?? 0)}</span>
            </div>
            <div class="divider my-1"></div>
            <ChemicalReadOnly field="ghrelin"        label="Ghrelin"        value={ne.ghrelin        ?? 400} unit="pg/mL" normalized={norm('ghrelin',        ne.ghrelin        ?? 400)} tooltip="Hunger hormone. Rises before meals." />
            <ChemicalReadOnly field="leptin"         label="Leptin"         value={ne.leptin         ?? 15}  unit="ng/mL" normalized={norm('leptin',         ne.leptin         ?? 15)}  tooltip="Satiety hormone from fat tissue." />
            <ChemicalReadOnly field="insulin"        label="Insulin"        value={ne.insulin        ?? 5}   unit="µU/mL" normalized={norm('insulin',        ne.insulin        ?? 5)}   tooltip="Glucose uptake regulator." />
            <div class="divider my-1"></div>
            <ChemicalReadOnly field="vasopressin"    label="Vasopressin"    value={ne.vasopressin    ?? 2}   unit="pg/mL" normalized={norm('vasopressin',    ne.vasopressin    ?? 2)}   tooltip="ADH — hydration regulation and social bonding." />
            <ChemicalReadOnly field="prolactin"      label="Prolactin"      value={ne.prolactin      ?? 8}   unit="ng/mL" normalized={norm('prolactin',      ne.prolactin      ?? 8)}   tooltip="Social bonding, stress response." />
            <ChemicalReadOnly field="growth_hormone" label="Growth Hormone" value={ne.growth_hormone ?? 1}   unit="ng/mL" normalized={norm('growth_hormone', ne.growth_hormone ?? 1)}   tooltip="Pulsatile — peaks during deep sleep. Anabolic, tissue repair." />
            <ChemicalReadOnly field="dhea"           label="DHEA"           value={ne.dhea           ?? 150} unit="µg/dL" normalized={norm('dhea',           ne.dhea           ?? 150)} tooltip="Anti-stress steroid. Buffers cortisol effects." />
          </div>
        </TierCard>
      </div>

    <!-- ═══════════════════════════════ IMMUNE / PAIN ═════════════════════════ -->
    {:else if activeTab === 'immune'}
      {@const im = data.immune ?? {}}
      {@const pa = data.pain  ?? {}}
      <div class="flex flex-col gap-4">
        <TierCard title="Immune">
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="il1b"      label="IL-1β"              value={im.il1b      ?? 2}   unit="pg/mL" normalized={norm('il1b',     im.il1b     ?? 2)}   tooltip="Pro-inflammatory. Triggers fever, fatigue, sickness behavior." />
            <ChemicalReadOnly field="il6"       label="IL-6"               value={im.il6       ?? 3}   unit="pg/mL" normalized={norm('il6',      im.il6      ?? 3)}   tooltip="Pro-inflammatory. Drives acute phase response." />
            <ChemicalReadOnly field="tnf_alpha" label="TNF-α"              value={im.tnf_alpha ?? 3}   unit="pg/mL" normalized={norm('tnf_alpha', im.tnf_alpha ?? 3)}  tooltip="Systemic inflammation, sickness withdrawal." />
            <ChemicalReadOnly field="crp"       label="C-Reactive Protein" value={im.crp       ?? 0.5} unit="mg/L"  normalized={norm('crp',      im.crp      ?? 0.5)} tooltip="Acute phase protein — systemic marker of active inflammation." />
            <ChemicalReadOnly field="il10"      label="IL-10"              value={im.il10      ?? 10}  unit="pg/mL" normalized={norm('il10',     im.il10     ?? 10)}  tooltip="Anti-inflammatory interleukin." />

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
          <div class="flex flex-col gap-3">
            <ChemicalReadOnly field="substance_p" label="Substance P"      value={pa.substance_p ?? 30} unit="pg/mL" normalized={norm('substance_p', pa.substance_p ?? 30)} tooltip="Primary nociceptive transmitter — carries pain signals to spinal cord." />
            <ChemicalReadOnly field="pge2"        label="Prostaglandin E2" value={pa.pge2        ?? 80} unit="pg/mL" normalized={norm('pge2',        pa.pge2        ?? 80)} tooltip="Sensitizes pain receptors. Produced during inflammation." />

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
                <div class="tooltip cursor-help" title="Higher vagal tone = better parasympathetic regulation.">
                  <span class="text-sm">Vagal Tone</span>
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
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Two-Process Sleep Model</h2>
            <p class="text-xs opacity-50 mb-1">Process S — Adenosine (Homeostatic Drive)</p>
            <ChemicalReadOnly field="adenosine" label="Adenosine" value={adeno} unit="nM" normalized={norm('adenosine', adeno)} tooltip="Homeostatic sleep pressure. Rises while awake, clears during sleep." />
            <div class="flex justify-between text-xs opacity-30 mt-1 mb-4">
              <span>15 rested</span><span>60 tired</span><span>80 onset</span><span>92 critical</span>
            </div>
            <p class="text-xs opacity-50 mb-1">Process C — Circadian Drive</p>
            <div class="flex flex-col gap-3">
              <ChemicalReadOnly field="melatonin" label="Melatonin" value={mel}    unit="pg/mL" normalized={norm('melatonin', mel)}    tooltip="Circadian sleep hormone. Peaks at night." dimmed={true} />
              <ChemicalReadOnly field="orexin"    label="Orexin"    value={orexin} unit="pg/mL" normalized={norm('orexin',    orexin)} tooltip="Wakefulness drive from lateral hypothalamus. Suppressed by adenosine." />
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
          </div>
        </div>

        <div class="flex flex-col gap-4">
          <div class="card bg-base-200 p-4">
            <h2 class="text-xs font-semibold opacity-50 uppercase tracking-wider mb-4">Circadian Phase</h2>
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
          <div class="flex flex-col gap-4">
            <div>
              <div class="flex justify-between items-center mb-1">
                <div class="tooltip text-left" data-tip="Brain-derived neurotrophic factor. Supports learning, memory, and neuronal survival.">
                  <span class="text-sm cursor-help">BDNF</span>
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
                <div class="tooltip text-left" data-tip="LTP/LTD balance — synaptic strength. High = learning active. Low = synaptic depression.">
                  <span class="text-sm cursor-help">Synaptic Potentiation</span>
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

          <!-- Bond / Social chart -->
          <div class="card bg-base-200 p-4">
            <LineChart
              title="Bond & Social"
              height={200}
              showSleep={true}
              {sleepBands}
              series={[
                {
                  key: 'oxytocin', label: 'Oxytocin (pg/mL)', color: '#f472b6',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.oxytocin ?? 0 }))
                },
                {
                  key: 'dopamine', label: 'Dopamine (ng/mL)', color: '#a78bfa',
                  minVal: 0, maxVal: 200,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.dopamine ?? 0 }))
                },
                {
                  key: 'serotonin', label: 'Serotonin (ng/mL)', color: '#34d399',
                  minVal: 0, maxVal: 40,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.serotonin ?? 0 }))
                },
                {
                  key: 'endorphins', label: 'Endorphins (AU)', color: '#fbbf24',
                  minVal: 0, maxVal: 40,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.endorphins ?? 0 }))
                },
                {
                  key: 'social_warmth', label: 'Social Warmth', color: '#fb923c',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.second_order?.social_warmth ?? 0 }))
                },
              ]}
            />
          </div>

          <!-- Stress / Arousal chart -->
          <div class="card bg-base-200 p-4">
            <LineChart
              title="Stress & Arousal"
              height={180}
              showSleep={true}
              {sleepBands}
              series={[
                {
                  key: 'cortisol', label: 'Cortisol (nM)', color: '#f87171',
                  minVal: 0, maxVal: 600,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.cortisol ?? 0 }))
                },
                {
                  key: 'norepinephrine', label: 'Norepinephrine (pg/mL)', color: '#fb923c',
                  minVal: 0, maxVal: 600,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.norepinephrine ?? 0 }))
                },
                {
                  key: 'anxiety', label: 'Anxiety', color: '#ef4444',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.third_order?.anxiety ?? 0 }))
                },
                {
                  key: 'arousal', label: 'Arousal', color: '#f59e0b',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.second_order?.arousal ?? 0 }))
                },
              ]}
            />
          </div>

          <!-- Wellbeing chart -->
          <div class="card bg-base-200 p-4">
            <LineChart
              title="Mood & Wellbeing"
              height={180}
              showSleep={true}
              {sleepBands}
              series={[
                {
                  key: 'mood_valence', label: 'Mood Valence', color: '#60a5fa',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.second_order?.mood_valence ?? 0 }))
                },
                {
                  key: 'hedonic_tone', label: 'Hedonic Tone', color: '#818cf8',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.second_order?.hedonic_tone ?? 0 }))
                },
                {
                  key: 'energy', label: 'Energy', color: '#4ade80',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.second_order?.energy ?? 0 }))
                },
                {
                  key: 'loneliness', label: 'Loneliness', color: '#94a3b8',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.third_order?.loneliness ?? 0 }))
                },
                {
                  key: 'depression', label: 'Depression', color: '#475569',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.third_order?.depression ?? 0 }))
                },
              ]}
            />
          </div>

          <!-- Inhibitory/Excitatory -->
          <div class="card bg-base-200 p-4">
            <LineChart
              title="Inhibitory / Excitatory & Cognition"
              height={160}
              showSleep={true}
              {sleepBands}
              series={[
                {
                  key: 'gaba', label: 'GABA (μM)', color: '#22d3ee',
                  minVal: 0, maxVal: 500,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.gaba ?? 0 }))
                },
                {
                  key: 'glutamate', label: 'Glutamate (μM)', color: '#f97316',
                  minVal: 0, maxVal: 200,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.glutamate ?? 0 }))
                },
                {
                  key: 'acetylcholine', label: 'Acetylcholine (nM)', color: '#a3e635',
                  minVal: 0, maxVal: 600,
                  points: history.map(s => ({ ts: s.ts, value: s.chemicals?.acetylcholine ?? 0 }))
                },
                {
                  key: 'cognitive_clarity', label: 'Clarity', color: '#e2e8f0',
                  minVal: 0, maxVal: 100,
                  points: history.map(s => ({ ts: s.ts, value: s.second_order?.cognitive_clarity ?? 0 }))
                },
              ]}
            />
          </div>

          <p class="text-xs opacity-30 text-center">Shaded bands = sleep periods. All series normalized to same 0–1 scale for comparison. Hover for raw values.</p>
        {/if}

      </div>
    {/if}

  {/if}
</div>
