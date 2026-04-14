/**
 * API helper — injects the Bearer token into every fetch call.
 * Also exports StateData v3 type definitions.
 */

let _token = (typeof localStorage !== 'undefined' ? localStorage.getItem('dashboard_token') : null) ?? '';
export function setToken(t: string) { _token = t; }
export function getToken(): string { return _token; }

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const t = token ?? _token;
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
      Authorization: `Bearer ${t}`,
    },
  });
  if (res.status === 401) {
    localStorage.removeItem('dashboard_token');
    window.location.reload();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) {
    return res.json() as Promise<T>;
  }
  return res.text() as unknown as Promise<T>;
}

// ---------------------------------------------------------------------------
// StateData v3 types
// ---------------------------------------------------------------------------

export interface ChemicalEntry {
  value:      number;
  unit:       string;
  label:      string;
  normalized: number;  // 0.0–1.0
}

export interface VitalEntry {
  value?:     number;
  systolic?:  number;
  diastolic?: number;
  unit:       string;
  label:      string;
}

export interface CascadeEvent {
  type:          string;   // "acth_release" | "cortisol_release"
  fires_at_unix: number;   // epoch seconds
  magnitude:     number;
}

export interface StateData {
  // Existing — unchanged
  chemicals:    Record<string, ChemicalEntry>;
  sleeping:     boolean;
  second_order: Record<string, number>;   // 0–100
  third_order:  Record<string, number>;   // 0–100
  vital_signs:  Record<string, VitalEntry>;

  // New tiers — all real values, normalized where noted
  neuroendocrine:       Record<string, number>;
  immune:               Record<string, number>;   // inflammation_index: 0–1
  pain:                 Record<string, number>;   // pain_intensity, central_sensitization, vagal_tone: 0–1
  neuroplasticity:      Record<string, number>;   // bdnf: ng/mL, allostatic_load: 0–1, synaptic_potentiation: 0–1
  personality_drift:    Record<string, number>;   // Big Five delta values
  body:                 Record<string, number>;   // core_temp °C, adenosine nM, circadian_phase 0–1
  receptor_sensitivity: Record<string, number>;   // 0.5–2.0 multiplier per receptor subtype
  cascade_queue:        CascadeEvent[];
  allostatic_load:      number;                   // 0.0–1.0
  cycle_day:            number;                   // 0–27
}

export interface TokenCall {
  input:     number;
  output:    number;
  reasoning: number;
  cached:    number;
}

export interface TurnEntry {
  turn:    number;
  ts:      number;
  calls:   Record<string, TokenCall>;
  totals:  TokenCall;
}

export interface TokenBudget {
  monthly_budget:      number;
  days_in_month:       number;
  daily_budget:        number;
  session_cost:        number;
  daily_pct:           number;
  input_price_per_m:   number;
  output_price_per_m:  number;
}

export interface TokenStats {
  session_start:   number | null;
  total_input:     number;
  total_output:    number;
  total_reasoning: number;
  total_cached:    number;
  turns:           number;
  by_label:        Record<string, TokenCall>;
  turn_log:        TurnEntry[];
  current_turn:    Record<string, TokenCall>;
  budget:          TokenBudget;
}
