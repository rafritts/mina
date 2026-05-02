# SPEC-50: Sim Viewer

## Overview

The Sim Viewer is the performative face of the simulation — not an admin tool, not a data dashboard. It is the experience of *watching Mina think and feel in real time*. The reference aesthetic is the Westworld control panel: the moment you see Maeve's vitals, her next words, her personality sliders — and realize you are watching a mind from the outside.

The viewer is not a fancier version of `/admin`. Admin is for intervention. The viewer is for witnessing.

**Route**: `/viewer`

**Lives in**: `ui/` — the Next.js 16 / React 19 app. Implemented as `ui/app/viewer/page.tsx` (App Router). The page must be a Client Component (`'use client'`) since it drives live WebGL, D3, and SSE.

**Design principle**: Everything in the viewer is a live artifact of the simulation. Nothing is decorative for its own sake. The topology shifts because her chemistry shifted. The graph node appears because a RAG hit fired. The text typewriters in because that is her response, being assembled.

Depends on SPEC-49 (Unified Data Stream) for its data feed.

---

## Layout

Full-screen. No persistent chrome — no topbar, no sidebar, no footer, no status bar. The viewport is the experience.

```
┌─────────────────────────────────────────────────────────┐
│  [Vanta Topology — full viewport background]            │
│                                                         │
│                                                         │
│         [Thought Graph — force-directed overlay]        │
│                                                         │
│              ┌──────────────────┐                       │
│              │  Response Node   │  ← central, typewriter│
│              └──────────────────┘                       │
│         ↗ RAG  ↑ Stimulus  ↑ Texture  ↗ Context        │
│                                                         │
│                                                         │
│  [≡ — visible on mouse movement only]                   │
└─────────────────────────────────────────────────────────┘
```

The graph occupies the center of the viewport. Topology fills everything behind it.

### Hamburger Nav

The `≡` icon appears in the bottom-left corner only while the mouse is moving (fade in on `mousemove`, fade out after 2s of inactivity). On click, a slim sidebar slides in from the left with a link to `/admin`. The graph and topology continue uninterrupted behind it.

---

## Vanta Topology Background

Vanta's `TOPOLOGY` effect fills the full viewport behind the graph layer, using the same initialization pattern and options as the existing `BackgroundAmbience` (DOTS). The `vanta.d.ts` type declaration for NET is removed; a TOPOLOGY declaration is added in its place.

### Baseline Color (Monoamine State)

The topology color at any moment is a weighted blend of monoamine colors, weighted by each monoamine's `normalized` value:

```ts
const MONOAMINE_COLORS: Record<string, [number, number, number]> = {
  dopamine:         [245, 158,  11],   // amber
  serotonin:        [ 96, 165, 250],   // soft blue
  norepinephrine:   [249, 115,  22],   // red-orange
  cortisol:         [ 74, 222, 128],   // cold green
  oxytocin:         [251, 113, 133],   // rose
  acetylcholine:    [167, 139, 250],   // violet
  gaba:             [ 45, 212, 191],   // deep teal
  endorphins:       [248, 200,  79],   // warm gold
  anandamide:       [134, 239, 172],   // mint
}

function blendMonoamineColor(chemicals: Record<string, ChemicalEntry>): [number, number, number] {
  let r = 0, g = 0, b = 0, total = 0
  for (const [name, rgb] of Object.entries(MONOAMINE_COLORS)) {
    const norm = chemicals[name]?.normalized ?? 0
    r += rgb[0] * norm
    g += rgb[1] * norm
    b += rgb[2] * norm
    total += norm
  }
  if (total === 0) return [80, 80, 100]  // neutral fallback
  return [r / total, g / total, b / total]
}
```

`ChemicalEntry` is the existing type from `ui/app/lib/api.ts`. This color is fed into Vanta's `color` option and recomputed on each `state_snapshot` event. The topology interpolates to the new color — it does not cut.

### Delta Pulses

`delta` events only fire when Mina receives a stimulus — not on the 10-second heartbeat tick. When a `delta` event arrives:

1. Compute the blend color of the changed chemicals (same formula, only chemicals with nonzero deltas)
2. Interpolate Vanta's color from the current baseline to the delta color over 0.4s
3. Hold for 0.3s
4. Interpolate back to the baseline over 2.5s

### Implementation Note

Vanta does not natively interpolate colors between calls. Maintain a `currentColor` ref and use `requestAnimationFrame` + linear interpolation to step toward the target, calling `effect.setOptions({ color: ... })` each frame.

---

## Thought Graph

A force-directed graph using **D3-force** (`d3-force` package). Nodes are sim artifacts. Edges connect input nodes to the central Response node. D3 handles the physics; React manages node state and renders the SVG overlay.

### Node Types

| Type | Source event | Description |
|------|-------------|-------------|
| `response` | `response_complete` | The final response text. Central node. |
| `stimulus` | `stimulus_land` | How the current message landed. |
| `context` | `context_snapshot` | The conversation context in use. |
| `rag` | `rag_hit` | One node per RAG result retrieved. |
| `kag` | `kag_selection` | One node per KAG file selected. |
| `texture` | `response_texture` | The tone/response-style instruction in effect. |

The sim produces a fixed number of each node type per turn — no cap or truncation needed.

### Graph Behavior

- **On new response cycle** (triggered by the first incoming event of a new turn, e.g. `stimulus_land`): all existing input nodes fade out over 500ms, then the graph clears.
- **As events arrive**: each new node fades in and pops into position quickly (~200ms transition). D3-force handles layout — nodes repel each other and are attracted to the response node at center.
- **Clustering**: nodes of the same type cluster together via a weak per-type cluster force.
- **Edges**: thin SVG lines connecting each input node to the response node. Appear with the node. Opacity ~0.2.
- **Response node**: larger, fixed at center. Text typewriters in when `response_complete` fires.

### Node Appearance

All nodes share a glassmorphism card treatment:

```
background: rgba(4, 4, 4, 0.75)
border: 1px solid rgba(255, 255, 255, 0.08)
backdrop-filter: blur(12px)
border-radius: 8px
```

Node width is proportional to text length, capped at ~300px. Text is small, muted. Per-type accent colors are TBD — to be iterated on during implementation. The response node is larger (~400px wide, fixed center).

### TypeWriter

The response node text typewriters in at ~35 chars/second. A blinking cursor appears while animating. When complete, the cursor disappears.

If a new cycle starts before the typewriter finishes, cancel it and fade immediately.

---

## SSE Subscription

The viewer subscribes to `/api/stream` (defined in SPEC-49) on mount via `EventSource`. Wrapped in `useEffect` with cleanup on unmount. On disconnect, retries with exponential backoff (cap at 30s, with jitter).

SSE event types must be defined in `ui/app/lib/api.ts` (or a new `ui/app/lib/stream.ts`) before implementation. The required types:

```ts
interface StateSnapshotEvent { type: 'state_snapshot'; chemicals: Record<string, ChemicalEntry>; second_order: Record<string, number>; third_order: Record<string, number> }
interface DeltaEvent        { type: 'delta'; chemicals: Record<string, ChemicalEntry> }
interface StimulusLandEvent { type: 'stimulus_land'; text: string }
interface ContextSnapshotEvent { type: 'context_snapshot'; text: string }
interface RagHitEvent       { type: 'rag_hit'; text: string }
interface KagSelectionEvent { type: 'kag_selection'; filename: string }
interface ResponseTextureEvent { type: 'response_texture'; text: string }
interface ResponseCompleteEvent { type: 'response_complete'; text: string }

type StreamEvent =
  | StateSnapshotEvent | DeltaEvent | StimulusLandEvent
  | ContextSnapshotEvent | RagHitEvent | KagSelectionEvent
  | ResponseTextureEvent | ResponseCompleteEvent
```

Events consumed:

| Event type | Action |
|------------|--------|
| `state_snapshot` | Recompute monoamine blend color, update topology baseline |
| `delta` | Trigger topology pulse for the changed chemicals |
| `stimulus_land` | Begin new cycle (fade old nodes), add stimulus node |
| `context_snapshot` | Add context node |
| `rag_hit` | Add a RAG node |
| `kag_selection` | Add a KAG node |
| `response_texture` | Add texture node |
| `response_complete` | Set response node text, start typewriter |

---

## Status Indicator

None. No persistent chrome over the viewport.

---

## Open Questions

1. **Vanta TOPOLOGY `setOptions` per-frame**: Calling `setOptions` every animation frame may cause Vanta to re-initialize its WebGL state internally. Needs to be tested early in implementation. If it does re-init, direct WebGL uniform injection or a throttled update (e.g. every 3 frames) may be needed.

2. **Status signal label (future)**: If a status indicator is added later, the signal label ("focused", "anxious") should be derived from the dominant `third_order` value at any given moment.
