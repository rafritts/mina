# Spec Manifest

Status legend: **DONE** · **IN-PROGRESS** · **TODO** · **DRAFT** (scoped but unfinished) · **OBE** (obsolete / superseded)

| SPEC | Title | Status | Notes |
|------|-------|--------|-------|
| 09 | Dashboard | DONE | Web dashboard with endpoints and frontend components |
| 10 | Chemical Architecture | DONE | Foundational registry, profiles, real units; v1→v2 migration path |
| 11 | Vital Signs | DONE | Derived vitals with formulas that prevent lethal states from raw chemistry |
| 12 | Social Expression Register | DONE | Expression filter by familiarity level with bleed-through mechanism |
| 13 | Personality Architecture | DONE | Big 5 as mechanical modifiers wired to neurochemistry; personality.json |
| 14 | Psychiatric States | MOTHBALLED | Episode-layer and medication profiles; not needed for current direction |
| 15 | Project Refactor | DONE | Structural refactor from flat root to `src/` package |
| 20 | Simulation Architecture Overhaul | DONE | BiologicalState v3, EventBus, label system, engine orchestration |
| 21 | Neurotransmitter Dynamics | DONE | GABA, glutamate, adenosine, anandamide, 2-AG + receptor sensitivity |
| 22 | Neuroendocrine & Metabolic | DONE | HPA axis, thyroid, sex hormones, metabolic hormones with cascade delays |
| 23 | Immune System & Pain | DONE | Cytokines, inflammation index, sickness behavior, gate-control pain |
| 24 | Neuroplasticity & Circadian | DONE | BDNF, allostatic load, two-process sleep, personality drift |
| 25 | Simulation Constants | DONE | Single source of truth for 500+ numeric params |
| 26 | Dashboard Overhaul | DONE | Six-tab layout, normalized chemistry display, HPA cascade viz |
| 27 | Stateless Decoder | DONE | 20-message window, RAG aging, context queue for encoder/decoder handoff |
| 28 | Social Connection | DONE | Decoupled loneliness/social_warmth, isolation pressure, extraversion modulation |
| 29 | Stimulus Habituation & Sensitization | DONE | Three-layer stimulus processing, content novelty, per-chemical secretion rules |
| 30 | Encoder Chemical Scope | DONE | Audit of acute vs tonic boundary; serotonin, acetylcholine, anandamide corrected |
| 31 | Social Isolation Deterioration | DONE | Multi-stage isolation model, bond-gated outreach, social_hostility |
| 32 | Single Source Truths | DONE | conversation.jsonl + hippocampus + bio_history.jsonl as three canonical stores |
| 33 | Relationship Knowledge | DONE | Cascading compaction hierarchy; six dimension scores feed relationship modifiers |
| 34 | Hedonic Setpoint & Craving | DONE | Allostatic setpoint, craving as derived value, post-high crash and withdrawal |
| 35 | Affective Memory Tagging | OBE | Superseded by SPEC-55 RAG overhaul |
| 37 | Stochastic Noise | OBE | Absorbed into SPEC-53; per-chemical noise_sigma + state-modulated scaling |
| 38 | Attachment Style | DRAFT | Four-style model (anxious/avoidant/disorganized/secure) behavioral deltas; flag planted |
| 39 | Context Coherence | OBE | Superseded by SPEC-55 RAG overhaul |
| 40 | Unidirectional Delta Correction | DONE | Encoder secretion-only enforced; floor saturation added; prolactin refractory in endocrine subsystem |
| 41 | Brain Region Architecture | DONE | stream_bus → application/infra, sim_baseline → application/tools; all imports updated |
| 42 | Epinephrine SAM Axis | DONE | Epinephrine registered, all 5 SAM moment types in encoder, recent exchanges block present |
| 43 | Bond Score | DRAFT | Persistent bond score separate from volatile oxytocin; open questions on approach |
| 44 | Normalized Chemistry Adjudicator | OBE | Adjudicator deleted by SPEC-52; normalized table no longer has a consumer |
| 45 | Sliding Window RAG | OBE | Superseded by SPEC-55 RAG overhaul |
| 46 | Hedonic Adaptation | TODO | Not started; old sensitization_level scalar still present; no session tracking or tonic offsets |
| 47 | Somatic Narrative | TODO | Not started; no somatic narrative, no [SOMATIC STATE] block, no somatic response field |
| 48 | Dashboard Admin Overhaul | DONE | Next.js 15 App Router on port 2050; art gallery aesthetic; FastAPI on 2049 |
| 49 | Unified Data Stream | DONE | StreamBus FIFO queue + SSE broadcaster; all modules emit via `emit()` |
| 50 | Sim Viewer | DONE | Full-screen viewer at /viewer; Vanta TOPOLOGY, D3 thought graph, SSE subscription |
| 51 | Response Reasoning | DONE | response_reasoner.py with internal_reaction, ResponseStrategy, follow-up queue; wired into cortex |
| 52 | Three-Pillar Pipeline | DONE | Emotion → Context → Response pipeline live; adjudicator removed; coherence files active |
| 53 | Sim Rule Consolidation | DONE | ChemicalProfile fields, generic clearance dispatch, stochastic noise, CompoundRule, resting-state validator |
| 54 | Biological Timing Model | DRAFT | Two-pool BBB separation; amygdala phasic (pre) + hypothalamus tonic (post) stimulus axes; 4 open questions |
| 55 | RAG Memory Overhaul | DRAFT | RAG is not producing useful results; flag planted; needs end-to-end audit before solution is designed |
| 99 | Long-Term Physiological Validation | OBE | Removed; sim_baseline.py (SPEC-53) covers validation needs |
