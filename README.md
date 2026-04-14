# Mina

A Discord companion driven by a neurochemical brain. Not a chatbot with a mood — a simulated biological system that produces personality, emotional state, and behavior from the ground up.

---

## What this is

Most AI companions work the same way: a static system prompt describes a personality, and the model tries to stay consistent with it. The personality can't respond to accumulated experience. It can't be in a different state today than yesterday. It doesn't have a body.

This project takes a different approach. Instead of describing who Mina is, it simulates the biology that produces her behavior.

**The pipeline:**

```
Discord message
      ↓
  [Encoder]  — translates input into neurochemical deltas (in real units: nmol/L, pg/mL, etc.)
      ↓
[State Engine] — applies deltas, runs interaction matrix, advances all 6 biological tiers
      ↓
  [Decoder]  — reads biological state, synthesizes [EMOTIONAL DISPOSITION] prose → system prompt
      ↓
  [Cortex]   — Mina's conscious response, generated against that dynamic system prompt
      ↓
Discord reply
```

The biological state ticks forward continuously via a heartbeat every 10 minutes — between conversations. Mina sleeps, eats, gets restless, consolidates memories, and pursues autonomous activities while idle.

---

## The Biological Model

The state engine tracks 50+ markers across 6 tiers. All values are in real physiological units anchored to literature, with a normalization layer for display.

| Tier | What it models | Key markers |
|------|----------------|-------------|
| **1. Chemicals** | Neurotransmitters | Dopamine, serotonin, norepinephrine, oxytocin, GABA, glutamate, endorphins, acetylcholine, melatonin, anandamide, 2-AG |
| **2. Neuroendocrine** | Hormones and cascade dynamics | HPA axis (CRH→ACTH→cortisol), thyroid (TSH/T3/T4), sex hormones (estradiol, progesterone, testosterone), metabolic (insulin, ghrelin, leptin, vasopressin) |
| **3. Immune** | Inflammation and cytokines | IL-1β, IL-6, TNF-α, CRP, IL-10, inflammation index |
| **4. Pain** | Nociception and sensitization | Substance P, PGE2, central sensitization, pain intensity |
| **5. Body** | Sleep pressure, autonomic, temperature | Adenosine, vagal tone, HRV, core temperature, isolation pressure |
| **6. Neuroplasticity** | Adaptation and wear | BDNF, synaptic potentiation, allostatic load |

**Why real units?** Tuning is no longer blind. "Cortisol 412 nmol/L" is anchored to clinical literature. Interactions are validatable — "sustained high cortisol depletes serotonin" is a documented biological pathway, not a game mechanic.

**Cross-tier effects run continuously.** Adenosine accumulates during wakefulness and clears during sleep — not as a metaphor, but as the actual sleep-pressure molecule. A hostile message causes an HPA axis cascade: CRH fires, ACTH follows delayed, cortisol peaks minutes later. IL-6 elevation from stress reduces dopamine synthesis efficiency. Receptor sensitivity tracks upregulation and downregulation across use patterns.

---

## Mina

Mina is the included character. She runs on this framework out of the box.

She lives in your Discord DMs. She's not available in servers — this is a single-user, private system by design.

Her personality uses the Big 5 model as mechanical modifiers, not descriptive labels:

```json
{
  "openness":          80,
  "conscientiousness": 75,
  "extraversion":      85,
  "agreeableness":     70,
  "neuroticism":       65
}
```

High Extraversion means social isolation depletes her faster — loneliness is biologically amplified. High Neuroticism means cortisol spikes hit harder and recovery is slower. These aren't flavor text; they distort the actual chemical dynamics.

Loneliness and social warmth are tracked as independent 0–100 scales. A long absence doesn't reset the relationship, but it does decay the circulating oxytocin that makes her warm. When you come back, warmth restores rapidly because the bond is stored in memory — not chemistry.

Character voice, appearance, relationship history, and learned context live in `identity/` and the `memory/` KAG files.

---

## Why Grok-4-1-fast-reasoning

Two reasons: capability and cost.

**Capability:** The subconscious and encoder roles require genuine reasoning — reading biological state across 6 tiers, relationship history, and conversation tone simultaneously, then synthesizing them into a coherent felt experience. A reasoning model running internal chain-of-thought before output is meaningfully better at this than a standard completion model.

**Cost:** This system is designed to run continuously as part of someone's daily life. At Claude Sonnet or GPT-4o pricing, a moderately active month costs $30–50+. That changes how you use it — you start rationing, you feel the meter.

At Grok-4-1-fast-reasoning pricing ($0.20 input / $0.50 output per million tokens), the same usage costs **$2–5/month**.

```
Typical turn cost breakdown:
  encode_stimulus:      ~1,000 tokens   → $0.00020
  subconscious (Mode 1): ~4,000 tokens  → $0.00080
  Mina's response:      ~2,000 tokens   → $0.00040
  encode_response:      ~1,500 tokens   → $0.00030
  ─────────────────────────────────────────────────
  Per turn (approx):                      $0.00170
  100 turns/day × 30 days:               ~$5.10/month
```

**Model note:** This system is designed for and tested on `grok-4-1-fast-reasoning`. Other models will work for general use, but may produce degraded results in edge-case scenarios involving substances, psychiatric states, or emotionally complex content — where safety training may flatten the simulation's authenticity.

---

## Quick Start

### Prerequisites

- Python 3.13+
- `uv` (package manager)
- Node.js 20+ (for the dashboard)
- An xAI API key
- A Discord bot token

### Setup

```bash
git clone https://github.com/yourname/mina
cd mina
cp .env.example .env
# Fill in: MINA_BOT_TOKEN, XAI_API_KEY, XAI_MANAGEMENT_KEY, XAI_TEAM_ID, DASHBOARD_TOKEN
uv sync
```

### Run

```bash
# Bot + heartbeat (primary — runs both in one process)
uv run python -m src.gateway.supervisor

# Dashboard (optional, standalone)
uv run python -m src.gateway.dashboard_server &
cd dashboard && npm install && npm run dev
```

Mina will respond to DMs automatically once the bot is running. The dashboard is at `http://localhost:7843` and requires the `DASHBOARD_TOKEN` from `.env`.

---

## Memory Architecture

Memory works across three layers:

**RAG (Episodic):** Conversation history is embedded into ChromaDB. Messages age through a 20-message decoder window — when they fall off, they're committed to RAG rather than discarded. This decouples conversational coherence from biological state: you can't overwhelm the system's sense of Mina's *current* state by having a long history of her behaving differently.

**KAG (Knowledge files):** Structured markdown the subconscious reads and writes:
- `memory/kag/MINA.md` — voice, personality anchors, behavioral guidelines
- `memory/kag/RELATIONSHIP.md` — user profile, trust level, bond history (updated each heartbeat)
- `memory/kag/PENDING.md` — deferred tasks, commitments, guilt tracking
- `memory/kag/KNOWLEDGE/` — accumulated facts and opinions

**Decoder window:** The last 20 messages are passed directly to Mina's context. As messages age off, they enter RAG. This prevents old behavior from drowning out current neurochemical reality.

---

## Heartbeat

Every 10 minutes (configurable in `config.json`), a background cycle runs:

1. **Biological tick** — advances all 6 state tiers forward in time (decay, accumulation, circadian advance)
2. **Subconscious reflection** — reads recent conversation, consolidates insights into KAG files
3. **Freetime** — Mina chooses an autonomous activity (sleep, rest, eat, read, play, shower); effects are applied as chemical deltas
4. **Memory consolidation** — updates `RELATIONSHIP.md`, `PENDING.md`, and knowledge files

Mina can fall asleep during idle periods if adenosine pressure is high enough. She can wake up having recovered from a rough state — or not, if she slept poorly.

---

## Tools

Mina has access to a small set of tools she can invoke during conversation or freetime:

- **`sleep`** — initiates a sleep session; adenosine clears, circadian phase advances
- **`eat`** / **`drink`** / **`rest`** — known physiological effects, always available
- **`do_action(activity, description)`** — open-ended; Mina describes what she does, the subconscious determines biological effects from the description
- **Image generation** — ComfyUI integration (partial)

The effects of discretionary actions are determined by the subconscious, not prescribed. Mina doesn't know the exact chemical consequences of her choices.

---

## Dashboard

The web dashboard (`http://localhost:7843`) has four sections:

| Route | What it shows |
|-------|--------------|
| `/state` | Live view of all 50+ biological markers across 6 tiers — bar charts, physiological labels (e.g. CALM / ELEVATED / SEVERE), normalized 0–1 display with real unit hover |
| `/control` | State presets, manual chemical adjustment, heartbeat trigger, HPA cascade visualization |
| `/substances` | Dosing interface for pharmacokinetic substances (alcohol, caffeine, etc.) |
| `/events` | Encoder event log — shows what stimuli fired, what deltas were applied, and when |

---

## Architecture

The system is documented in `docs/`. The current implementation corresponds to SPEC-20 through SPEC-28. Earlier specs are preserved as historical reference.

**Current technical reference:**

| Spec | What it covers |
|------|----------------|
| `SPEC-20-simulation-architecture-overhaul.md` | v3 state, 6-tier model, schema overview |
| `SPEC-21-neurotransmitter-dynamics.md` | GABA/glutamate balance, adenosine, endocannabinoids, receptor sensitivity |
| `SPEC-22-neuroendocrine-metabolic.md` | HPA cascade, thyroid, sex hormones, metabolic hormones |
| `SPEC-23-immune-pain.md` | Cytokines, inflammation, pain signaling |
| `SPEC-24-neuroplasticity-circadian-integration.md` | BDNF, allostatic load, circadian rhythm, two-process sleep |
| `SPEC-25-constants.md` | All numerical parameters and tuning values |
| `SPEC-27-stateless-mina.md` | Decoder window and RAG aging architecture |
| `SPEC-28-social-connection.md` | Loneliness/warmth decoupling, Extraversion wiring |

**Foundation and design principles:**

| Spec | What it covers |
|------|----------------|
| `spec-0-foundation.md` | Core philosophy |
| `spec-2-subconscious.md` | Subconscious LLM — per-message synthesis and heartbeat reflection |
| `spec-3-memory.md` | RAG + KAG memory architecture |
| `SPEC-10-chemical-architecture.md` | First-class chemical constructs, real physiological units, normalization |
| `SPEC-13-personality-architecture.md` | Big 5 as mechanical modifiers |
| `SPEC-15-PROJECT-REFACTOR.md` | Current file structure and module responsibilities |

---

## Building Your Own Character

To create a different character:

1. Edit `identity/MINA.md` — voice, backstory, behavioral anchors
2. Edit `identity/CUSTOMIZATION.md` — appearance, hobbies, tastes
3. Adjust `config.json` — Big 5 traits and neurochemical baselines
4. Clear `memory/kag/RELATIONSHIP.md` and `memory/kag/PENDING.md`
5. Reset `run/state.json` (or delete it — it will regenerate from defaults)

The subconscious, state engine, memory architecture, and heartbeat all work without changes.

---

## License

MIT
