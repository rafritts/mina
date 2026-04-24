# SPEC-50: Sim Viewer

## Overview

The Sim Viewer is the performative face of the simulation — not an admin tool, not a data dashboard. It is the experience of *watching Mina think and feel in real time*. The reference aesthetic is the Westworld control panel: the moment you see Maeve's vitals, her next words, her personality sliders — and realize you are watching a mind from the outside.

The viewer is not a fancier version of `/admin`. Admin is for intervention. The viewer is for witnessing.

**Route**: `/viewer`

**Design principle**: Everything in the viewer is a live artifact of the simulation. Nothing is decorative for its own sake. The topology shifts because her chemistry shifted. The graph node appears because a RAG hit fired. The text typewriters in because that is her response, being assembled.

Depends on SPEC-49 (Unified Data Stream) for its data feed.

---

## Layout

Full-screen. The nav panel is collapsed by default — a single toggle icon in a corner. No topbar, no sidebar, no footer. The viewport is the experience.

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
│  [≡ toggle]                    [status dot + signal]    │
└─────────────────────────────────────────────────────────┘
```

The graph occupies the center of the viewport. Topology fills everything behind it.

---

## Vanta Topology Background

Vanta's `TOPOLOGY` effect fills the full viewport behind the graph layer.

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

function blendMonoamineColor(chemicals: ChemicalState): [number, number, number] {
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

This color is fed into Vanta's `color` option and recomputed on each state snapshot. The topology slowly interpolates to the new color — it does not cut.

### Delta Pulses

When a `delta` event arrives from the SSE stream, the topology pulses to the color of the monoamine(s) that changed:

1. Compute the blend color of the deltas (same blending formula, using only the chemicals that have nonzero deltas)
2. Interpolate Vanta's color from the current baseline to the delta color over 0.4s
3. Hold for 0.3s
4. Interpolate back to the baseline monoamine blend over 2.5s

This creates a constant pulse: the background "breathes" every time her neurochemistry shifts, with the color of what shifted.

### Implementation Note

Vanta does not natively interpolate colors between calls. We maintain a `currentColor` ref and use `requestAnimationFrame` + linear interpolation to step toward the target color, calling `effect.setOptions({ color: ... })` each frame.

---

## Thought Graph

A force-directed graph rendered via D3-force (or a lightweight alternative). Nodes are sim artifacts. Edges connect input nodes to the central Response node.

### Node Types

| Type | Source | Description |
|------|--------|-------------|
| `response` | `response_complete` event | The final response text. Central node. |
| `stimulus` | `stimulus_land` event | How the current message landed. |
| `context` | `context_snapshot` event | The conversation context being used. |
| `rag` | `rag_hit` event | One node per RAG result retrieved. |
| `kag` | `kag_selection` event | One node per KAG file selected. |
| `texture` | `response_texture` event | The tone/response-style instruction in effect. |

### Graph Behavior

- **On new response cycle**: all existing input nodes fade out (opacity → 0, 0.5s), then the graph clears. The response node becomes the new central node for the incoming cycle.
- **As events arrive**: each input node fades in and floats into position. D3-force handles layout — nodes repel each other and are attracted to the center.
- **Clustering**: nodes of the same type cluster together. RAG nodes group on one side, KAG on another, etc. Achieved by adding a weak cluster force per type.
- **Edges**: thin lines connecting each input node to the response node. Appear when the node appears. Opacity ~0.2.
- **Response node**: larger, centered, distinct styling. Text typewriters in character by character when the `response_complete` event fires.

### Node Appearance

Each node type has a distinct color and style, but all share the same glassmorphism card treatment:

```
background: rgba(4, 4, 4, 0.75)
border: 1px solid rgba(255, 255, 255, 0.08)
backdrop-filter: blur(12px)
border-radius: 8px
```

Node width is proportional to text length, capped at ~300px. Text is small, muted. The response node is larger (~400px wide, centered).

### TypeWriter

The response node text typewriters in at ~35 chars/second. A blinking cursor appears while the animation is running. When complete, the cursor disappears.

If a new response cycle starts before the current typewriter finishes, cancel and fade immediately.

---

## SSE Subscription

The viewer subscribes to `/api/stream` (defined in SPEC-50) on mount. On disconnect, it retries with exponential backoff.

Events consumed:

| Event type | Action |
|------------|--------|
| `state_snapshot` | Recompute monoamine blend color, update topology baseline |
| `delta` | Trigger topology pulse for the changed chemicals |
| `stimulus_land` | Add/update stimulus node |
| `context_snapshot` | Add/update context node |
| `rag_hit` | Add a new RAG node |
| `kag_selection` | Add a new KAG node |
| `response_texture` | Add/update texture node |
| `response_complete` | Set response node text, start typewriter, begin new cycle countdown |

---

## Collapsed Nav

A single `≡` icon in the bottom-left corner. On click, a slim sidebar slides in from the left with links to `/admin` and back. It does not interrupt the viewer — the graph and topology continue behind it.

---

## Status Indicator

Bottom-right corner: a small dot (colored by current dominant monoamine blend) + the computed signal label ("focused", "anxious", etc.). Small, muted, non-intrusive.

---

## Open Questions

1. **D3-force vs alternatives**: D3-force is the standard choice for force-directed graphs. Alternatives like `react-force-graph` add React integration but more bundle weight. Evaluate at implementation time.

2. **Vanta color interpolation performance**: Calling `setOptions` per-frame may cause Vanta to re-initialize internally. Need to test whether direct WebGL uniform injection is possible or if there is a cheaper path.

3. **Node overflow**: A long RAG context with 5+ results could crowd the graph. May need to cap visible nodes per type (e.g. max 3 RAG nodes, replacing oldest).

4. **Mobile**: Not a priority for v1. The viewer is designed for desktop.

5. **KAG data availability**: KAG currently logs which files were selected but not their content snippets. SPEC-50 should surface at least the filename and a short excerpt if available.
