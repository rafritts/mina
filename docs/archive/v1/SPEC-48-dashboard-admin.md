# SPEC-48: Dashboard Overhaul — Admin Interface

## Overview

Full replacement of the SvelteKit dashboard with a Next.js 15 App Router application using shadcn/ui. The admin interface is the control room: all existing functionality preserved, information hierarchy radically improved, aesthetics upgraded to match the quality of the project.

The Sim Viewer (SPEC-49) builds on top of this — get the architecture right here first.

---

## Aesthetic: Art Gallery

The admin is an art gallery. Not a stage — a gallery.

The distinction matters: the Sim Viewer (SPEC-49) is an opera stage — something performs at you, enveloping and theatrical. The admin is a space you move through deliberately. You have agency. Each piece rewards your attention when you approach it.

**Implications for every design decision:**

- **Lighting is spotlights on pieces, not stage wash.** Each card has a simulated ceiling spot: a subtle `radial-gradient(ellipse at 50% 0%, rgba(255,255,255,0.06) 0%, transparent 60%)` from its top edge. The card brightens on hover as if a dimmer has been nudged up. The surrounding space recedes.

- **Negative space is intentional.** Gallery walls give each piece room to breathe. Data is not packed. Groups are separated with generous margin. What's absent is as deliberate as what's present.

- **Interactivity is "leaning in."** On hover, a card lifts subtly toward you (CSS 3D `perspective` + `rotateX/Y` — 3–5° maximum). A secondary layer of detail appears (the number that was hidden, the label that was muted). You chose to engage; it rewards you without demanding attention from across the room.

- **The reactive signal is ambient, not theatrical.** When the dominant signal shifts, the gallery's lighting temperature shifts slowly — the background hue, the spotlight color on cards. But no piece moves, pulses, or performs. The work is still; the light around it changes.

- **Navigation is moving through rooms.** Page transitions are not slides — they are the room coming into focus (opacity fade, subtle scale). Each page is a room with a clear theme and stays within it. The sidebar reads like gallery wing labels, not a feature list.

**Background:** `#07070a` — near-black, slight cool undertone. SVG noise grain at 3% opacity. A very faint radial vignette lighter at the content center, darker at the edges — the gallery corridor is lit, the walls recede.

**Typography:**
- UI labels, navigation, descriptions: **Geist** (clean, contemporary)
- All values and data readouts: **Geist Mono** — numbers feel like instrument readouts, not text
- Primary text: `#e8e4dd` (warm white, like paper under gallery light — not pure white)
- Secondary text: `rgba(232, 228, 221, 0.45)`

**No 3D rendering engine on admin.** Depth comes from CSS perspective transforms and lighting gradients only. The viewer owns WebGL; the admin stays lightweight enough to run in a background tab all day.

---

## Port Assignments

| Service | Port | Rationale |
|---------|------|-----------|
| FastAPI API | **2049** | Blade Runner 2049 — the android film |
| Next.js UI | **2050** | One step further into the future |

Update `dashboard_server.py`: change Uvicorn bind port from current to `2049`. Remove static file serving entirely — the dashboard is no longer served from FastAPI.

---

## Architecture

```
discord / mina CLI
       ↓
FastAPI :2049  ←──────────────── Next.js :2050
  /api/state                        /admin/*
  /api/events                       next.config.ts rewrites:
  /api/history                        /api/* → localhost:2049/api/*
  /api/substance/*
  /api/heartbeat
  /api/billing
  /api/tokens
```

Next.js is a standalone server (`output: 'standalone'`). It proxies all `/api/*` requests to FastAPI via `rewrites` in `next.config.ts`. No CORS changes needed — same-origin from the browser's perspective.

**FastAPI changes:**
- Remove `app.mount("/", StaticFiles(...))` and the SPA fallback route
- Remove `dashboard/build/` dependency entirely
- Change port to 2049
- Keep all API endpoints unchanged

---

## Directory Structure

```
ui/                          ← replaces dashboard/
  package.json
  next.config.ts
  tsconfig.json
  tailwind.config.ts
  components.json            ← shadcn config
  src/
    app/
      layout.tsx             ← root layout: sidebar + topbar shell
      page.tsx               ← redirect to /admin
      admin/
        layout.tsx           ← admin shell with sidebar nav
        page.tsx             ← Overview (redirect or inline)
        neuro/
          page.tsx           ← Neurotransmitters
        physiology/
          page.tsx           ← Hormones, immune, pain, body
        history/
          page.tsx           ← Recharts timeseries
        control/
          page.tsx           ← Heartbeat, advance, presets, cascade
        substances/
          page.tsx           ← Substance dose management
        events/
          page.tsx           ← Event stream
        system/
          page.tsx           ← Billing, tokens, uptime
    components/
      ui/                    ← shadcn generated components
      charts/                ← Recharts wrappers
      metrics/               ← ChemicalCard, DerivedMeter, etc.
      layout/                ← Sidebar, Topbar, NavLink
    lib/
      api.ts                 ← fetch client (port 2049)
      types.ts               ← all TypeScript interfaces (from api.ts)
      labels.ts              ← display names, ranges, colors (port from labels.ts)
      hooks/
        useStatePoller.ts    ← shared polling hook (2s interval)
        useHistoryPoller.ts  ← history polling (30s interval)
```

---

## Information Hierarchy

The core problem with the current dashboard: 30+ chemicals shown at equal weight. The new admin organizes information in three tiers of importance:

### Tier 1 — Always Visible (Topbar)
A persistent strip across every admin page:
- **Dominant state badge** — computed from second-order metrics (e.g. "Focused", "Anxious", "Resting", "Elevated")
- **Sleeping indicator** — pill badge, green when awake
- **Last heartbeat** — relative time ("3m ago")
- **Alert indicators** — small colored dots if any chemical is in warning/critical range

### Tier 2 — Overview Page (`/admin`)
The landing page. Not a redirect — an actual view:
- Six **second-order metric cards** (energy, clarity, hedonic_tone, social_warmth, arousal, mood_valence) — large, prominent, with trend arrows
- Seven **third-order metric cards** (anxiety, depression, boredom, loneliness, flow, physical_distress, craving) — smaller, grouped
- **Recent events** — last 5 events from `/api/events`, inline
- **System health** — token usage, last update timestamp

### Tier 3 — Drill-Down Pages
Individual pages for specifics. Not dumped together.

---

## Pages

### `/admin` — Overview
- Second-order metrics as large stat cards (shadcn Card + Progress)
- Third-order metrics as a 3-column grid of smaller cards
- Last 5 events panel (right sidebar or bottom)
- Token usage summary

### `/admin/neuro` — Neurotransmitters
Chemicals organized by functional group, not alphabetically:

| Group | Chemicals |
|-------|-----------|
| Monoamines | dopamine, serotonin, norepinephrine |
| Bonding / Social | oxytocin, endorphins |
| Modulators | acetylcholine, anandamide, 2-ag |
| Excitatory / Inhibitory | glutamate, gaba |
| Stress | cortisol |

Each chemical: current value + unit, label (from RANGES), editable slider (shadcn Slider) inline. Save button per row appears only when value changes (no global save).

Receptor sensitivities in a collapsible section below — table format, not sliders (these are less frequently touched).

### `/admin/physiology` — Physiology
Three tab sections:
- **Hormones** — neuroendocrine fields (read-only display, normalized bar)
- **Immune** — IL-1β, IL-6, TNF-α, CRP, IL-10, inflammation_index
- **Body** — core_temp, adenosine, anandamide, 2-AG, isolation_pressure, circadian_phase, pain metrics

Read-only display with value + label. No sliders here — these aren't directly editable in the current system.

### `/admin/history` — History
Recharts `LineChart` with time range selector (1h, 6h, 24h, 7d). Chart groups:

- **Monoamines**: dopamine, serotonin, norepinephrine
- **Stress**: cortisol, norepinephrine
- **Derived**: energy, hedonic_tone, mood_valence, anxiety
- **Social**: oxytocin, social_warmth

Toggle which group is shown. No dumping all chemicals on one chart.

Data from `GET /api/history` with limit determined by time range selection.

### `/admin/control` — Control
- **Heartbeat** — large button, spinner while running, status display
- **Advance Simulation** — hour input + button (shadcn Input + Button)
- **Presets** — grid of preset cards (name, description, apply button). Current presets from `presets.ts` ported over.
- **Cascade Queue** — live-updating list of pending biochemical events (5s poll)
- **Quick Inject** — select chemical + value + inject (for dev use)

### `/admin/substances` — Substances
Table view: substance name, current dose level, half-life indicator, Dose button, Clear button. From `/api/substance`.

### `/admin/events` — Events
Event stream with filter bar (stimulus | response | activity | tool). Each event:
- Timestamp (relative + absolute on hover)
- Type badge
- Preview text
- Chemical deltas as inline colored tags (Δ+2.3 dopamine)
- Expandable row for full detail

Auto-refresh toggle (5s interval). Load more button for history.

### `/admin/system` — System
- **Billing** — xAI cap, used, remaining (shadcn Progress bar)
- **Token usage** — breakdown by call type (table)
- **Uptime / health** — last successful heartbeat, state file age

---

## Subtle Reactivity

The admin has a quiet version of the theming system (the full version lives in SPEC-49):

- The sidebar accent color softly shifts based on dominant second-order state
- High cortisol: border/ring accents shift toward red-900
- High dopamine: accents shift toward amber-700
- Baseline: the default shadcn zinc/slate dark

This is implemented via CSS custom properties on the root `<html>` element, updated by the polling hook. Transitions are slow (2–3s ease) so it's ambient, not jarring.

```ts
// in useStatePoller.ts — after each poll
function applyThemeHint(state: StateData) {
  const dopNorm = state.chemicals.dopamine?.normalized ?? 0
  const cortNorm = state.chemicals.cortisol?.normalized ?? 0
  const oxy = state.chemicals.oxytocin?.normalized ?? 0

  const dominant = Math.max(dopNorm, cortNorm, oxy)
  let hue = 0 // neutral

  if (cortNorm === dominant && cortNorm > 0.6) hue = 0    // red
  else if (dopNorm === dominant && dopNorm > 0.6) hue = 38  // amber
  else if (oxy === dominant && oxy > 0.6) hue = 340         // rose

  document.documentElement.style.setProperty('--accent-hue', String(hue))
}
```

Tailwind is configured with `hsl(var(--accent-hue) ...)` for the accent color class.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | Next.js 15, App Router |
| Language | TypeScript |
| Components | shadcn/ui (dark theme, zinc base) |
| Styling | Tailwind CSS 4 |
| Charts | Recharts |
| Animations | Framer Motion (page transitions, metric updates) |
| HTTP | native fetch with Bearer token |
| State | React hooks + polling (no external store) |

shadcn theme: `dark`, base color `zinc`. This gives the cold, precise aesthetic appropriate for a monitoring tool.

---

## Migration Plan

### Phase 1 — Scaffold
1. Delete `dashboard/` directory entirely
2. Create `ui/` with `npx create-next-app@latest` (TypeScript, Tailwind, App Router, no src alias confusion)
3. Install shadcn: `npx shadcn@latest init`
4. Install Recharts, Framer Motion
5. Set up `next.config.ts` rewrites for `/api/*` → `http://localhost:2049/api/*`
6. Port `api.ts` types and fetch client
7. Port `labels.ts` display metadata

### Phase 2 — Layout Shell
1. Root layout: sidebar nav, topbar, main content area
2. Sidebar: nav links to all 7 admin pages
3. Topbar: dominant state badge, sleeping indicator, last heartbeat, alert dots
4. Implement `useStatePoller` hook (2s interval)
5. Wire subtle theme reactivity

### Phase 3 — Pages (in order)
1. Overview page
2. Neurotransmitters
3. Events (high value, quick win)
4. History (Recharts setup)
5. Control
6. Substances
7. Physiology
8. System

### Phase 4 — FastAPI Port Migration
1. Update `dashboard_server.py`: port 2049, remove static file serving
2. Update any hardcoded port references in `config.py`, CLI, Discord gateway
3. Update `mina start/stop/restart` scripts if they reference the old port

### Phase 5 — Verification
1. Run `npm run dev` on port 2050
2. Confirm all API endpoints proxy correctly
3. Test auth flow
4. Confirm `mina restart` / Discord `/restart` still work (they hit FastAPI, not the UI — no change needed there)

---

## Files Touched

| File | Change |
|------|--------|
| `dashboard/` | Deleted entirely |
| `ui/` | New Next.js application |
| `src/application/gateway/dashboard_server.py` | Port 2049, remove static file serving |
| `src/infra/config.py` | Update `DASHBOARD_PORT` constant if it exists |
| Any scripts referencing port 7843 | Update to 2049 |

---

## Open Questions

1. **Auth in Next.js**: The current system uses a Bearer token stored in localStorage, passed via URL param on first load. This pattern works identically in Next.js — no change needed. Confirm before implementing.

2. **`next export` vs standalone**: Using `output: 'standalone'` (full server). This enables future SSE/WebSocket support for the Sim Viewer. Static export would prevent that.

3. **Port in `mina` CLI**: Find all places the dashboard port is referenced in CLI commands and update.
