# Control / Lab action map (RES-125)

Where each former Control-tab and duplicated Lab action lives after the shell (RES-122) and this dedupe. Feeds [RES-124](https://linear.app/restlessapi/issue/RES-124). Inventory ids are from [ADR 0001](adr/0001-unified-workspace-ia.md) §1 and §4.

Nothing in §4 was dropped. Twins were collapsed onto one home. Scene vs Turn trace, ThoughtStream vs Turn trace, and Clear vs Erase stay separate.

## Former Control pane

The pane (`ControlPane.tsx`, tabs Presence / Chemistry / Tools) is gone. `C-control-toggle`, `C-control-desktop`, and `C-control-drawer` stay retired. `/admin/control` still redirects to `/`.

| ID | Former action | Home now |
|----|---------------|----------|
| C-pres-sleep | Consciousness / sleep card, plus the footer awake/sleeping word | **Sleep** card. Compact on the status-pill **Presence** sheet; page-size on **Overview**. Shared `SleepStatusCard` (`ui/app/components/presence/SleepStatusCard.tsx`) and `sleepStatusLines`. The footer no longer repeats awake/sleeping. Header pill stays `presenceLabel` plus Thinking / Offline. |
| C-pres-felt | Felt-state bars (energy, mood, warmth, clarity, arousal, hedonic) | Same six fields. Compact bars on the Presence sheet; cards on Overview. Shared `FeltMetricList`. |
| C-pres-signals | Signals bars (anxiety, low mood, boredom, loneliness, flow, distress) | Same six fields, same component, same two densities. |
| C-pres-ft | Free-time peek (chips, relative time, two-line body) and “Open Free time” | **Presence sheet only** (`FreetimePeek`). Up to 4 chips (the richer of the two old peeks), polled every 15s while the sheet is open. Link: Open Free time → `/admin/freetime`. |
| C-chem-mono, C-chem-bond, C-chem-stress, C-chem-sleep, C-chem-other | Chemistry sliders + Set | **Chemistry** route only (`/admin/neuro`). No second slider list. Groups live in `ui/app/lib/chem-groups.ts`. |
| C-preset | Mood presets (Baseline, Euphoria, Flow, Loved, Anxious, Despair, Lonely, Tender, Irritable, Sleepy) | Header **Tools** sheet. |
| C-advance | Advance sim time (0.25–168h, step 0.25, default 1) | Header **Tools** sheet. |
| C-heartbeat | Run freetime heartbeat | Header **Tools** sheet. **System** keeps last-run / running status only. |
| C-reset | Reset chemistry to baseline (confirm: keeps chat & memory) | Header **Tools** sheet. Confirm unchanged. |
| C-erase | Erase conversation history (confirm lists transcript, scene, diary, RAG, relationship, free-time sessions) | Header **Tools** sheet. Still fires `mina:erase-chat`. Confirm unchanged. |
| C-lab-link | “Open Lab…” | Primary nav. No cross-app link. |

## Former Lab duplicates

| ID | Former action | Home now |
|----|---------------|----------|
| L-ov-title | Overview title = `presenceLabel` | Overview, unchanged. |
| L-ov-sleep | Overview sleep card (twin of Control) | Overview page-size `SleepStatusCard`. Same copy as the sheet. |
| L-ov-felt, L-ov-signals | Overview metric cards (twin of Control bars) | Overview cards via `FeltMetricList` `variant="card"`. |
| L-ov-ft | Overview free-time peek (up to 4 chips) + “Open Free time” | Removed from Overview so it is not a second peek. The same peek is the Presence sheet (`C-pres-ft`). The Free time page is still the session log. |
| L-ov-events | Recent events strip (8) + View all | Overview, unchanged. |
| L-chem-* | Chemistry editors, secretion queue, receptor table | Chemistry route only. Union below. |
| L-ft-empty | Empty copy pointed at Control → heartbeat | Free time empty state points at the header **Tools** sheet (Run freetime heartbeat) and says reset and erase live on that sheet. System is status only. |
| L-sys-hb | Heartbeat last run + running | System page, status only. The run action is Tools. |

These Lab pages were not twins of Control and are unchanged: Turn trace (`/admin/context`), Free time session list and pillar dump, History, Events, System build / billing / tokens.

## Chemistry union

One editor, `CHEM_EDITOR_GROUPS`:

| Group | Chemicals |
|-------|-----------|
| Monoamines | dopamine, serotonin, norepinephrine |
| Bonding & social | oxytocin, endorphins |
| Stress | cortisol, epinephrine, **crh** (Control had listed crh under Other) |
| Sleep & clock | adenosine, melatonin, orexin |
| Other peptides | anandamide, ghrelin, **substance_p**, **vasopressin** |

`substance_p` and `vasopressin` were missing from Control. A row still renders from `DISPLAY_RANGES` if the sim snapshot omits the key. Secretion queue and receptor sensitivities stay on this page only.

## Kept as two reaches

| Pair | Why |
|------|-----|
| Scene dialog vs Turn trace | Clothing, positions, fiction-now, timeline, plans, inject vs the last pillar assembly. |
| ThoughtStream vs Turn trace | Per-message mind in the thread vs the latest full dump. |
| Clear vs Erase vs Reset | Clear empties the chat store view. Erase wipes transcript, scene, diary, RAG, relationship, and free-time sessions. Reset restores baseline chemistry and keeps chat and memory. |
| Free-time peek vs Free time page | Peek is the latest line on the Presence sheet. The page is the session list, tools, diary, and copy. |

## Shared components

| Component | Used by |
|-----------|---------|
| `ui/app/components/presence/SleepStatusCard.tsx` | Presence sheet (`compact`), Overview (`page`) |
| `ui/app/components/presence/FeltMetricList.tsx` | Presence sheet (`bar`), Overview (`card`) |
| `ui/app/components/presence/FreetimePeek.tsx` | Presence sheet only |
| `ui/app/lib/chem-groups.ts` | Chemistry route only |
| `ui/app/components/metrics/StatBar.tsx` | Chemistry readout (unchanged) |
| `ui/app/components/metrics/DerivedCard.tsx` | Still unused. Not a new page. |
