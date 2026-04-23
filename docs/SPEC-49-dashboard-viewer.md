# SPEC-49: Dashboard Overhaul — Sim Viewer

## Overview

The Sim Viewer is the open source pitch. It is the thing you screenshot for the README. It is what someone sees the first time they run Mina and opens a browser. It needs to make them feel like they are watching a real biological system breathe.

It is not a data dashboard with nice styling. It is an ambient display that happens to contain data.

The design principle: **information is present but recessive**. The emotional state of the simulation is primary. Numbers and labels are secondary — they appear when you look for them, not before.

Builds on SPEC-48 (admin infrastructure, port assignments, Next.js setup).

---

## Route

`/` — the root. The viewer is the default experience. Admin is the tool you reach for when you need to intervene.

---

## Core Concept: The Dominant Signal

Every 2 seconds, the poller computes a **dominant signal** from the current biological state. This single value drives the entire visual language of the viewer.

```ts
type DominantSignal = {
  id: 'calm' | 'focused' | 'excited' | 'stressed' | 'anxious' | 'melancholic' | 'warm' | 'depleted' | 'altered'
  intensity: number        // 0–1, how strongly this signal dominates
  transition: number       // ms for CSS transitions (calm = slow, stressed = fast)
  palette: SignalPalette
}

type SignalPalette = {
  bg: string               // e.g. 'hsl(220 15% 6%)'  — near-black background hue
  primary: string          // e.g. 'hsl(38 90% 55%)'  — the dominant glow/accent
  secondary: string        // e.g. 'hsl(38 60% 30%)'  — muted version
  particle: string         // particle system color
  pulseSpeed: number       // animation duration multiplier (1.0 = normal)
}
```

### Signal Computation

```ts
function computeDominantSignal(state: StateData): DominantSignal {
  const dop = state.chemicals.dopamine?.normalized ?? 0
  const cort = state.chemicals.cortisol?.normalized ?? 0
  const sero = state.chemicals.serotonin?.normalized ?? 0
  const oxy = state.chemicals.oxytocin?.normalized ?? 0
  const gaba = state.chemicals.gaba?.normalized ?? 0
  const ne = state.chemicals.norepinephrine?.normalized ?? 0
  const ananda = state.chemicals.anandamide?.normalized ?? 0

  const anxiety = (state.third_order?.anxiety ?? 50) / 100
  const hedonic = (state.second_order?.hedonic_tone ?? 50) / 100
  const energy = (state.second_order?.energy ?? 50) / 100

  if (state.sleeping) return { id: 'calm', intensity: 0.8, ... }
  if (cort > 0.7 && ne > 0.6) return { id: 'stressed', ... }
  if (anxiety > 0.7) return { id: 'anxious', ... }
  if (dop > 0.65 && energy > 0.6) return { id: 'excited', ... }
  if (dop > 0.5 && cort < 0.4) return { id: 'focused', ... }
  if (oxy > 0.6 && sero > 0.5) return { id: 'warm', ... }
  if (hedonic < 0.35 && energy < 0.4) return { id: 'melancholic', ... }
  if (ananda > 0.6 || gaba > 0.65) return { id: 'altered', ... }
  if (energy < 0.3) return { id: 'depleted', ... }
  return { id: 'calm', ... }
}
```

### Signal Palettes

| Signal | Background | Primary | Feel |
|--------|-----------|---------|------|
| `calm` | deep slate, cool | steel blue | quiet, slow pulse |
| `focused` | dark charcoal | amber | warm light, steady |
| `excited` | dark warm | bright amber → gold | fast, energized |
| `stressed` | near-black | deep crimson | tight, sharp pulse |
| `anxious` | dark cool | orange-red | jittery, irregular |
| `melancholic` | very dark blue-grey | muted indigo | slow, fading |
| `warm` | dark warm-black | rose | soft glow, gentle |
| `depleted` | almost black | grey-blue | very slow, dim |
| `altered` | dark teal-black | green | dreamy, slow wave |

All palettes stay dark — this is always a dark room. The signal changes the *color and intensity of the light*, not the darkness of the space.

---

## Layout

Full-screen, no traditional navigation chrome. The viewer owns the whole viewport.

```
┌──────────────────────────────────────────────────────┐
│  [subtle top strip: name, sleeping status, signal]    │  ~40px
├──────────────────────────────────────────────────────┤
│                                                      │
│              PARTICLE FIELD / AMBIENT BG             │  ~45vh
│                                                      │
│         [CENTRAL PRESENCE — large emotional          │
│          state display, radial glow]                 │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│   [METRIC CONSTELLATION — floating cards]            │  ~35vh
│                                                      │
├──────────────────────────────────────────────────────┤
│  [RECENT EVENT TICKER — subtle bottom strip]         │  ~40px
│  [admin link — bottom right corner]                  │
└──────────────────────────────────────────────────────┘
```

---

## Components

### Particle Field

Full-viewport Canvas element behind everything. `tsParticles` or a custom `requestAnimationFrame` canvas renderer.

Particle behavior responds to dominant signal:
- **calm**: ~40 particles, slow drift, low opacity (0.15), large radius, no connections
- **focused**: ~60 particles, directional drift (upward), amber, faint connection lines between near particles
- **excited**: ~120 particles, fast random motion, bright, connection lines active, occasional burst clusters
- **stressed**: ~80 particles, erratic motion, tight clusters, red-orange, collision-like behavior
- **melancholic**: ~20 particles, very slow fall, low opacity, no connections
- **sleeping**: ~15 particles, circular slow drift, blue-silver, almost invisible

Transition: particle count, speed, and color lerp smoothly over 3–5 seconds when signal changes. No hard cuts.

### Central Presence

The dominant visual element. A large (~300px diameter) radial element centered in the upper portion of the viewport.

Composed of:
1. **Core glow** — a soft `radial-gradient` circle with the primary signal color, pulsing in opacity (Framer Motion `animate` with `repeat: Infinity`)
2. **Orbital rings** — 2–3 SVG circles, very thin stroke, rotating slowly at different speeds and radii. Rotation speed scales with `pulseSpeed`.
3. **State label** — the signal name in large, spaced, light-weight typography centered in the core. Not a technical label — a human word. ("focused" not "DOPAMINE_ELEVATED")
4. **Intensity arc** — a single arc around the outer ring, length proportional to signal intensity. Changes color with signal.

The pulse period:
- calm: 4s
- focused: 2.5s
- excited: 1.2s
- stressed: 0.8s (feels urgent)
- melancholic: 6s
- sleeping: 8s

### Metric Constellation

The data layer. Floating cards arranged in a loose arc below the central presence. These are the "information is present but recessive" elements.

**What's shown:**
- Six second-order metrics (energy, clarity, hedonic_tone, social_warmth, arousal, mood_valence)
- Two or three key chemicals that are notably elevated or depressed (not all of them)
- One third-order metric if any is significantly elevated (e.g. anxiety > 70, loneliness > 65)

**How it's shown:**
- Small frosted-glass cards (~140px wide), minimal border, subtle backdrop blur
- Metric name in small caps, muted color
- Value as a thin arc progress indicator (not a number — a visual fill)
- The number appears only on hover (Framer Motion layout animation)
- Cards that are "elevated" glow faintly with the signal color
- Cards that are "depleted" are slightly more transparent

Cards are not in a grid — they float in a loose arrangement. Position shifts subtly (Framer Motion spring) when signal changes.

**Which chemicals surface:**
```ts
function selectSurfacedChemicals(state: StateData): string[] {
  // surface chemicals that are notably off-baseline (normalized > 0.65 or < 0.25)
  return Object.entries(state.chemicals)
    .filter(([_, v]) => v.normalized > 0.65 || v.normalized < 0.25)
    .sort((a, b) => Math.abs(b[1].normalized - 0.5) - Math.abs(a[1].normalized - 0.5))
    .slice(0, 3)
    .map(([k]) => k)
}
```

### Event Ticker

A subtle bottom strip. Single line, monospace-ish font, small size, muted color.

Shows the most recent encoder event: type badge + preview text. New events fade in, replacing the previous one. If no events in 60 seconds, shows nothing (empty ticker).

Not clickable here — events detail lives in admin.

### Top Strip

40px bar:
- Left: name ("Mina") in small, light text
- Center: sleeping indicator when sleeping (moon icon + "sleeping"), otherwise invisible
- Right: signal label + soft colored dot

No navigation, no buttons. The only navigation element is a small "admin →" link in the bottom-right corner.

---

## Signal Transitions

When the dominant signal changes, nothing cuts hard. Everything transitions:

1. Background color: CSS `transition: background 3s ease`
2. Particle behavior: over 3 seconds, lerp particle count/speed/color
3. Central glow: Framer Motion `animate` with spring physics, 2s settle
4. Orbital ring speed: CSS animation duration changes, transition over 2s
5. Metric card glows: Framer Motion layout animation, 0.8s

The only exception: if cortisol spikes very fast (Δ > 0.3 in one poll), the transition to `stressed` is faster (0.5s) — mimicking the urgency of an acute stress response.

---

## Sleeping State

When `state.sleeping === true`:

- Particle count drops to minimum over 10 seconds
- Orbital rings slow to near-stop
- Central glow dims to 15% opacity
- Background shifts to deepest dark (almost black)
- State label shows "sleeping" in very small, italic text
- A slow pulse (8s period) continues — she's alive, just resting
- Metric constellation opacity drops to 40% — the data is present, barely

---

## Implementation Notes

### Canvas vs CSS

The particle field should use a `<canvas>` element with `requestAnimationFrame` rather than a library, to keep the bundle small and have full control over lerp behavior during signal transitions. tsParticles is fine if the lerp behavior is acceptable, but it adds ~50kb.

### No SSR for the viewer

The viewer is a client-only page. Mark it with `'use client'` throughout. The canvas and animation dependencies don't work in SSR.

### Polling

Reuse `useStatePoller` from SPEC-48. The viewer and admin use the same hook — they are separate pages, each mounting their own instance. No shared state store needed.

### Performance

The particle canvas should run at 30fps (not 60) to reduce CPU load on machines that may have this open all day. Use `setTimeout` inside `requestAnimationFrame` to cap frame rate.

---

## Tech Stack Additions (on top of SPEC-48)

| Addition | Purpose |
|----------|---------|
| Framer Motion | Orbital ring animation, card transitions, glow pulse |
| Custom Canvas renderer | Particle field |
| `@radix-ui/react-tooltip` | Hover-to-reveal metric values (via shadcn Tooltip) |

No Three.js — the 3D effect comes from CSS perspective transforms on the floating cards and the radial glow depth, not actual WebGL. This keeps the page lightweight enough to run in a background tab all day.

---

## Files Touched (additions to SPEC-48 `ui/`)

| File | Purpose |
|------|---------|
| `src/app/page.tsx` | Viewer (was redirect, now full component) |
| `src/components/viewer/ParticleCanvas.tsx` | Canvas particle field |
| `src/components/viewer/CentralPresence.tsx` | Radial glow + orbital rings + state label |
| `src/components/viewer/MetricConstellation.tsx` | Floating metric cards |
| `src/components/viewer/EventTicker.tsx` | Bottom event strip |
| `src/lib/signal.ts` | `computeDominantSignal()`, palette definitions |

---

## Open Questions

1. **Particle library vs custom canvas**: tsParticles has good lerp support via `refresh()` API. Worth evaluating before writing a custom renderer.

2. **Mobile**: The viewer is designed for a desktop that's open in the background. Mobile layout is not a priority for v1.

3. **WebSocket vs polling**: The viewer would benefit from SSE/WebSocket push from FastAPI for instant chemical spike reactions (instead of waiting up to 2s). Worth adding a `/api/stream` SSE endpoint in FastAPI — the Next.js standalone server can proxy it. Not required for v1 but natural follow-on.

4. **Sound**: A subtle ambient drone that shifts frequency with dominant signal would complete the experience. Out of scope for v1 — flagged for future.
