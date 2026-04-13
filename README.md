# Mina

A Discord companion with a neurochemical brain. Not a chatbot with a mood — a simulated biological system that drives personality, emotional state, and behavior from the ground up.

---

## What this is

Most AI companions work the same way: a static system prompt describes a personality, and the model tries to stay consistent with it. The personality can't actually respond to accumulated experience. It can't be in a different state today than yesterday. It doesn't have a body.

This project takes a different approach. Instead of describing who Mina is, it simulates the biology that produces her behavior:

- A neurochemical state engine tracks cortisol, dopamine, serotonin, oxytocin, norepinephrine, endorphins, acetylcholine, melatonin, glucose, hydration, and sleep pressure — all in real physiological units
- A cross-chemical interaction matrix models the slow biological feedback loops (sustained cortisol depletes serotonin; oxytocin suppresses the HPA axis; etc.)
- Circadian rhythms, substance pharmacokinetics with half-lives and withdrawal, and vital signs (heart rate, blood pressure, respiration, SpO2) are derived from the chemical state
- A separate subconscious LLM call runs before every response — it reads the biological state and translates it into Mina's felt experience, then generates her system prompt for that turn
- A memory architecture (RAG + long-term KAG files) accumulates relationship history, personality evolution, and learned context over time

The result: behavior that emerges from state rather than being scripted. Hunger makes her irritable through the actual mechanism — glucose drops, cortisol spikes, serotonin degrades, she reads neutral inputs as slights. A long absence doesn't reset the relationship, but it does decay the circulating oxytocin that makes her warm — and when you come back, it restores rapidly because the bond is stored in memory, not chemistry. A bad night compounds into a bad morning compounds into a bad week if nothing improves.

---

## Mina

Mina is the included character preset. She runs on this framework out of the box — you don't need to configure anything to have a working companion.

She lives in your Discord DMs. She's not available in servers — this is a single-user, private system by design.

Her personality, voice, appearance (ComfyUI integration included), relationship dynamics, and neurochemical baseline are all preconfigured. She's a complete character, not a template.

If you want to build your own character instead, Mina's configuration files are the reference. The framework is generic — swap the identity files, adjust the Big 5 profile and neurochemical baselines in `personality.json`, and you have a different person.

---

## Why Grok-4-1-fast-reasoning

Two reasons: capability and cost.

**Capability:** The subconscious role requires genuine reasoning — reading biological state, relationship context, and conversation tone simultaneously and synthesizing them into a coherent felt experience. A reasoning model that runs internal chain-of-thought before producing output is meaningfully better at this than a standard completion model. Grok-4-1-fast-reasoning is built for exactly this kind of multi-factor inference.

**Cost:** This system is designed to run continuously as part of someone's daily life. At Claude Sonnet or GPT-4o pricing, a moderately active month of usage runs $30–50+. That's a meaningful recurring cost that changes how you use the system — you start rationing, you feel the meter running.

At Grok-4-1-fast-reasoning pricing ($0.20 input / $0.50 output per million tokens), the same usage costs **$2–5/month**. A full day of active conversation is under a dollar. You can run the heartbeat, the subconscious, and the main response pipeline continuously without thinking about it.

```
Typical turn cost breakdown:
  encode_stimulus:     ~1,000 tokens   → $0.00020
  subconscious Mode 1: ~4,000 tokens   → $0.00080
  Mina's response:     ~2,000 tokens   → $0.00040
  encode_response:     ~1,500 tokens   → $0.00030
  ─────────────────────────────────────────────────
  Per turn (approx):                     $0.00170
  100 turns/day × 30 days:              ~$5.10/month
```

**Model compatibility note:** This system is designed for and tested on `grok-4-1-fast-reasoning`. Other models will work for general use but may produce degraded results in edge-case scenarios involving substances, psychiatric states, or emotionally complex content — where other models' safety training may intervene in ways that flatten the simulation's authenticity.

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
# Fill in XAI_API_KEY and DISCORD_BOT_TOKEN in .env
uv sync
```

### Run

```bash
# Bot + heartbeat (primary)
uv run python -m src.gateway.supervisor

# Dashboard (optional, standalone)
uv run python -m src.gateway.dashboard_server &
cd dashboard && npm install && npm run dev
```

Mina will respond to DMs automatically once the bot is running. The dashboard is available at `http://localhost:7843` and requires the `DASHBOARD_TOKEN` from your `.env`.

---

## Architecture

The system is documented in detail across the spec files in `docs/`. Reading order:

| Spec | What it covers |
|---|---|
| `spec-0-foundation.md` | Core philosophy and design principles |
| `spec-1-state-engine.md` | Current state engine (pre-refactor reference) |
| `SPEC-10-chemical-architecture.md` | First-class chemical constructs, real physiological units, normalization layer |
| `SPEC-11-vital-signs.md` | Heart rate, blood pressure, respiration, SpO2 — derived from chemistry |
| `SPEC-12-social-expression-register.md` | Familiarity-gated filter between internal state and expressed behavior |
| `SPEC-13-personality-architecture.md` | Big 5 as mechanical modifiers — end state where MINA.md collapses to ~200 words |
| `SPEC-14-psychiatric-states.md` | Episode modifiers, medications, blunting, drug interactions |
| `spec-2-subconscious.md` | The subconscious LLM — per-message synthesis and heartbeat reflection |
| `spec-3-memory.md` | RAG + KAG memory architecture |
| `spec-5-heartbeat.md` | Autonomous background cycle |
| `SPEC-09-dashboard.md` | Web dashboard for monitoring and control |

---

## Building Your Own Character

Everything Mina-specific lives in `characters/mina/`. To create a new character:

1. Copy `characters/mina/` to `characters/yourname/`
2. Edit `personality.json` — set Big 5 traits, neurochemical baselines, and optionally a psychiatric condition
3. Edit `identity/MINA.md` — the character's voice, backstory, and behavioral anchors
4. Edit `identity/APPEARANCE.md` — physical description and ComfyUI generation tags
5. Point `config.json` at your new character directory

The subconscious, state engine, memory architecture, and heartbeat all work without changes.

---

## Dashboard

The web dashboard (`http://localhost:7843`) provides real-time visibility and control:

- Live neurochemical values with physiological labels and bar charts
- Vital signs (heart rate, blood pressure, respiration, SpO2)
- Inner monologue viewer
- Relationship file viewer
- Subconscious injection (one-shot context inserted into the next turn)
- Direct chemical adjustment via sliders

Some advanced features in the dashboard are opt-in and not enabled by default.

---

## License

MIT
