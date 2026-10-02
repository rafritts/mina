# ADR 0001 — One workspace: Chat is home, Lab is surfaces

**Status:** Proposed (information architecture only). No UI behavior changes in this PR.

**Date:** 2026-10-02

**Deciders:** Ryan Fritts (product). This ADR records the locked Option C decision and the route-level map for implementation.

**Tickets:**

| Ticket | Role |
|--------|------|
| [RES-120](https://linear.app/restlessapi/issue/RES-120) | Parent: unify Chat + Lab. Option C is locked. |
| [RES-121](https://linear.app/restlessapi/issue/RES-121) | This document. |
| [RES-122](https://linear.app/restlessapi/issue/RES-122) | Implement the shell. Do not start here. |
| [RES-123](https://linear.app/restlessapi/issue/RES-123) | Visual tokens / density. Out of scope. |
| [RES-124](https://linear.app/restlessapi/issue/RES-124) | No-drop acceptance. Use §4 as the seed checklist. |
| [RES-125](https://linear.app/restlessapi/issue/RES-125) | Control ↔ Lab dedupe. Implemented. Outcome is §3 below and [docs/res-125-action-map.md](../res-125-action-map.md). |

**Stack constraint:** Next.js + shadcn. This ADR does not change components, tokens, or APIs.

---

## Decision

Mina is **one workspace**. Chat (`/`) is home. Every Lab page stays a route inside that same shell (sidebar on wide screens, drawer on narrow). The header **Chat | Lab** switch goes away. There is no second app to “go to,” and no “← Back to Chat” exit.

Nothing in the inventory is deleted. Surfaces move; actions stay reachable. URL paths under `/admin/*` stay until a later rename (not this epic’s IA work).

Rejected:

- **Option A** — an explicit Lab mode you enter and leave.
- **Option B** — Chat-only, with Lab features folded into the composer or dropped.

---

## Current chrome (verified on `master`)

Two layouts share `AppRoot` + `AppHeader` and then diverge.

| Piece | Where | What it does today |
|-------|--------|--------------------|
| Wordmark | `ui/app/components/shell/AppHeader.tsx` | `Link` to `/`. Always visible, including mobile. |
| Primary nav | same file, `PRIMARY_NAV` | **Chat** (`/`) and **Lab** (`/admin`). Class `hidden sm:flex` — **absent below 640px**. |
| Status pill | same | Chat (`ui/app/components/ChatApp.tsx`): Thinking / Offline / Sleeping / Live. Lab (`ui/app/admin/layout.tsx`): `presenceLabel()` (Sleeping, Anxious, Elevated, Focused, Warm, Low, Depleted, Present) plus poll age. |
| Chat body | `ui/app/page.tsx` → `ChatApp` | Message column. Control is a third column at `lg+` when open, and a right drawer below `lg`. |
| Lab body | `ui/app/admin/layout.tsx` | `lab-sidebar` (hidden below 640px) with 7 links and “← Back to Chat”. `lab-main`. `lab-mobile-nav` (7 labels, no Chat item; hidden at `sm+`). |
| Bookmark | `ui/app/admin/control/page.tsx` | `/admin/control` redirects to `/`. Control already lives in Chat. |

Competing surfaces a person hits today: header Chat\|Lab, header Context / Clear / Control, Control’s three tabs, per-turn ThoughtStream, composer image prefs, `ChatContextModal` (four sections), Lab’s seven destinations, and each Lab page’s own sections. That is the sprawl Option C collapses.

---

## 1. Capability inventory

IDs are stable for RES-124. “Home” in §4 is the proposed surface, not a new route unless noted.

### 1.1 Chat — route `/`

Mounted by `ui/app/page.tsx` → `ui/app/components/ChatApp.tsx`.

#### Shell actions (header)

| ID | Capability | Code |
|----|------------|------|
| C-status | Connection / turn status pill: Thinking while sending, Offline when the stream is down, Sleeping when `state.sleeping`, otherwise Live | `ChatApp` `status` / `statusLabel` |
| C-context-open | Open the scene modal | Header button “Context” |
| C-clear | Clear the on-screen transcript and flush the shared chat store to `[]`. Does **not** call `/api/conversation/erase` | `clearView` |
| C-control-toggle | Show/hide Control. Preference `localStorage` key `mina-control-open` | `setControlOpen` |
| C-control-desktop | At `lg+`, Control is an inline right column | `hidden lg:flex` |
| C-control-drawer | Below `lg`, Control is a right drawer with backdrop close | `control-drawer-backdrop` |

#### Message stream

| ID | Capability | Code |
|----|------------|------|
| C-empty | Empty state (“Say something real.”) | `ChatApp` empty block |
| C-send | Composer send. Enter sends; Shift+Enter newline. Disabled while a turn is in flight | `send` / `onKeyDown` |
| C-edit | Edit **the last user message** only; resubmits as a redo/rewind | `UserMessage`, `handleEdit` |
| C-redo | Redo an assistant reply from the preceding user text | `handleRedo` |
| C-error | Inline error alert | `error` banner |
| C-persist | Messages + image prefs persist via the chat store (`ui/app/lib/chat-store-api.ts`). Legacy `localStorage` keys `mina-chat-messages` / `mina-chat-prefs` migrate once | hydrate / `flushRemoteStore` |
| C-erase-event | Listens for `mina:erase-chat` (fired by Control → Erase) and clears the local transcript | `ChatApp` effect |

#### Images

| ID | Capability | Code |
|----|------------|------|
| C-img-count | Pics this reply: Auto, 0, 1–5. Sent as `image_count`. Stored with the chat store | `ui/app/components/ImageCountSelector.tsx`, `ui/app/lib/image-count.ts` |
| C-img-aspect | Landscape / square / portrait. Disabled when count is 0. Sent as `image_aspect` | `ui/app/components/AspectRatioSlider.tsx`, `ui/app/lib/image-aspect.ts` |
| C-img-render | Host images pulled out of reply markdown (`/images/…`, `/api/generate/…`) with captions | `splitMessageMedia` |
| C-img-pending | “Photo still rendering” placeholder | `PhotoPending` |
| C-img-fail | Failed-load alert | `ChatImage` |
| C-lightbox | Click to enlarge. Prev/next, filmstrip, open original, download, close | `ui/app/components/Lightbox.tsx` |

#### ThoughtStream (mind stream)

`ui/app/components/ThoughtStream.tsx`. Live while a turn runs; archived and collapsible on the assistant bubble (newest open, older ones collapse).

| ID | Capability | Code |
|----|------------|------|
| C-mind-live | Live pipeline panel, typewriter, always expanded. Fallback “Pipeline starting…” | `ThoughtStream` `live` |
| C-mind-archive | Collapsible “Mind” row with one-line summary (affect · approach · tone) | `mindSummary` |
| C-mind-rail | Stage rail: Sense, Chem, Feel, Memory, Situate, Decide, Speak | `STAGES` |
| C-mind-chem | Chem · appraisal → Class-1: flags, encoder axes, applied deltas (nM), quiet-turn copy | `MindBody` encoder section |
| C-mind-feel | Insula · felt state: affect, trend, availability, summary, somatic, drive | emotion section |
| C-mind-memory | Memory · what surfaces (up to 5; KAG vs recall) | memory section |
| C-mind-situate | Hippocampus · situation: social context, urgency, summary, notable | context section |
| C-mind-decide | PFC · internal monologue: reaction, approach, tone, lead-with | reasoning section |
| C-mind-silence | Completed skipped turn labeled “Chose silence” | `mind.skipped` |

Sense is a rail step only; the stimulus is the user bubble.

#### ChatContextModal (scene — not the Lab Context page)

`ui/app/components/ChatContextModal.tsx`. Portal dialog. Loads `GET /api/scene`. Escape and backdrop close. This is **short-term narrative coherence**, not the pillar dump.

| ID | Capability | Section |
|----|------------|---------|
| C-scene-refresh | Refresh | header |
| C-scene-live | Live Scene: fiction now, clothing cards, position cards, empty hint | `scene` |
| C-scene-timeline | Timeline of past beats; latest row marked | `timeline` |
| C-scene-plans | Plans (fuzzy commitments) | `plans` |
| C-scene-inject | “What she gets”: system prompt or inject, Copy | `inject` |
| C-scene-jump | Section chips scroll to Live Scene / Timeline / Plans / What she gets | `SECTIONS` |

#### Control pane — `ui/app/components/ControlPane.tsx`

Polls sim state every 2.5s (`useStatePoller`). Header shows `presenceLabel`, a Stream connected/disconnected pill, and close (drawer only). Footer shows “updated Ns ago” and sleeping/awake. Toasts on actions. Offline copy tells you to start `uv run python main.py`.

**Tab: Presence**

| ID | Capability |
|----|------------|
| C-pres-sleep | Consciousness card: `sleepStatusLines` (title, detail, since/elapsed or last bout) + Sleeping/Awake pill |
| C-pres-ft | Latest free-time session: up to 3 tool chips, relative time (clock on hover), two-line body. Empty: “No free-time sessions yet.” Link “Open Free time lab →” → `/admin/freetime`. Polled every 15s |
| C-pres-felt | Felt state bars for `SECOND_ORDER`: energy, mood, warmth, clarity, arousal, hedonic (`ui/app/lib/presence.ts`) with range chips |
| C-pres-signals | Signals bars for `THIRD_ORDER`: anxiety, low mood, boredom, loneliness, flow, distress |

**Tab: Chemistry** — sliders + Set, `PATCH /api/state`. Groups in `CHEM_GROUPS`:

| ID | Group | Chemicals |
|----|--------|-----------|
| C-chem-mono | Monoamines | dopamine, serotonin, norepinephrine |
| C-chem-bond | Bonding | oxytocin, endorphins |
| C-chem-stress | Stress | cortisol, epinephrine |
| C-chem-sleep | Sleep & clock | adenosine, melatonin, orexin |
| C-chem-other | Other | anandamide, crh, ghrelin |

Each row: label chip (tooltip = implication), value + unit, range slider, Set when dirty, gap vs circadian target and normalized /10. Chip stays on the last server label while the slider is dirty.

**Tab: Tools**

| ID | Capability | API |
|----|------------|-----|
| C-preset | Mood presets from `ui/app/lib/presets.ts`: Baseline, Euphoria, Flow, Loved, Anxious, Despair, Lonely, Tender, Irritable, Sleepy | `PATCH /api/state` |
| C-advance | Advance sim time, hours input 0.25–168 step 0.25, default 1 | `POST /api/state/advance` |
| C-heartbeat | “Run freetime heartbeat” | `POST /api/heartbeat` |
| C-reset | “Reset chemistry to baseline” — confirm: keeps chat & memory | `POST /api/state/reset` |
| C-erase | “Erase conversation history” — confirm: transcript, scene, diary, RAG, who you are to her, free-time sessions. Then `mina:erase-chat` | `POST /api/conversation/erase` |
| C-lab-link | “Open Lab for history, context & system →” | `/admin` |

### 1.2 Lab — routes under `/admin/*`

Layout: `ui/app/admin/layout.tsx`. Nav order:

1. Overview `/admin` (exact)
2. Chemistry `/admin/neuro`
3. Context `/admin/context`
4. Free time `/admin/freetime`
5. History `/admin/history`
6. Events `/admin/events`
7. System `/admin/system`

Plus the redirect `/admin/control` → `/`.

#### L-overview — `ui/app/admin/page.tsx`

| ID | Capability |
|----|------------|
| L-ov-title | Page title = `presenceLabel` |
| L-ov-sleep | Same sleep card as Control Presence |
| L-ov-ft | Free-time peek (up to 4 chips) + “Open Free time →” |
| L-ov-felt | Felt state as metric **cards** (same six `SECOND_ORDER` fields) |
| L-ov-signals | Signals as metric cards (same six `THIRD_ORDER` fields) |
| L-ov-events | Recent events, limit 8, type chip + preview + relative time. “View all” → `/admin/events` |

#### L-chem — `ui/app/admin/neuro/page.tsx`

Same slider + Save (`PATCH /api/state`) pattern, rendered with `StatBar` (`ui/app/components/metrics/StatBar.tsx`): colored bar, implication **text** (not only a tooltip), gap, normalized /10.

| ID | Group | Chemicals |
|----|--------|-----------|
| L-chem-mono | Monoamines | dopamine, serotonin, norepinephrine |
| L-chem-bond | Bonding & social | oxytocin, endorphins |
| L-chem-stress | Stress | cortisol, epinephrine, **crh** |
| L-chem-sleep | Sleep & clock | adenosine, melatonin, orexin |
| L-chem-other | Other peptides | anandamide, ghrelin, **substance_p**, **vasopressin** |
| L-chem-queue | Secretion queue table: chemical, remaining, rate/hr. Empty state | `state.secretion_queue` |
| L-chem-receptors | Receptor sensitivities table | `state.receptor_sensitivity` |

`substance_p` and `vasopressin` are on this page and **not** in Control’s `CHEM_GROUPS`. `crh` is under Stress here and under Other in Control.

#### L-turn — `ui/app/admin/context/page.tsx` (Lab “Context”)

Latest **pillar assembly** (`GET /api/context`, markdown `GET /api/context/text`). This is not `ChatContextModal`.

| ID | Capability |
|----|------------|
| L-turn-live | Live / paused auto-refresh (4s) |
| L-turn-refresh | Manual refresh |
| L-turn-copy | Copy markdown, copy JSON |
| L-turn-raw | Toggle raw markdown vs sections |
| L-turn-meta | Timestamp, relative age, source, username, skipped-reply flag |
| L-turn-msg | User message |
| L-turn-enc | Encoder (amygdala) key/values + `relationship_modifier` |
| L-turn-dec | Decoder table: norm, setpoint, gap, rate per chemical + Big 5 |
| L-turn-asm | Context assembly: window synthesis, RAG, KAG, raw retrieval (sliding + episodic) |
| L-turn-ins | Insula (emotion) |
| L-turn-hip | Hippocampus (situation) |
| L-turn-pfc | PFC (strategy) |
| L-turn-sys | System prompt Mina sees |
| L-turn-reply | Reply, or “(silence)” when skipped |
| L-turn-empty | 404 copy: “No assembly yet — send a chat message first.” |

#### L-ft — `ui/app/admin/freetime/page.tsx`

| ID | Capability |
|----|------------|
| L-ft-live | Live / paused (8s) |
| L-ft-refresh | Refresh list, detail, markdown |
| L-ft-copy | Copy markdown, copy JSON |
| L-ft-raw | Raw markdown toggle |
| L-ft-list | Session list (up to 50): relative time, duration, up to 3 chips, two-line body. Selecting loads detail |
| L-ft-meta | Clock time, relative time, duration, tool labels, pillars / “no pillar dump” |
| L-ft-msg | Synthetic input |
| L-ft-tools | Tools & diary (`record_diary` prose, other tool args, result). Badge = tool count |
| L-ft-reply | Reply / note |
| L-ft-enc | Encoder + relationship modifier, or “no pillar dump” |
| L-ft-dec | Decoder table + Big 5 |
| L-ft-asm | Assembly: window, RAG, KAG, raw retrieval |
| L-ft-ins | Insula |
| L-ft-hip | Hippocampus |
| L-ft-pfc | PFC |
| L-ft-sys | System prompt |
| L-ft-empty | Empty copy points at Control → Tools → Run freetime heartbeat |

#### L-hist — `ui/app/admin/history/page.tsx`

`useHistoryPoller`. Recharts line chart.

| ID | Capability |
|----|------------|
| L-hist-range | Windows: 1h, 6h, 24h, 7d (default 6h) |
| L-hist-groups | Series groups: Monoamines (dopamine, serotonin, norepinephrine), Stress (cortisol, norepinephrine), Derived (energy, hedonic tone, mood valence, anxiety), Social (oxytocin, social warmth) |
| L-hist-chart | Time axis, tooltip, legend. Empty: “No history samples yet” |

#### L-events — `ui/app/admin/events/page.tsx`

| ID | Capability |
|----|------------|
| L-ev-filter | Filters: all, activity, tool, stimulus, response |
| L-ev-auto | Auto-refresh checkbox (5s), default on |
| L-ev-row | Type chip, preview/result/tool text, up to 5 delta chips, relative time (absolute on hover) |
| L-ev-expand | Row click expands full text |
| L-ev-more | “Load more” raises the limit from 100 to 500 |

#### L-sys — `ui/app/admin/system/page.tsx`

| ID | Capability | Source |
|----|------------|--------|
| L-sys-build | Build id, git, built-at | `ui/app/lib/build-info.ts` |
| L-sys-bill | Billing used / cap bar, percent, remaining. Warns past 60% and 80% | `GET /api/billing` |
| L-sys-hb | Heartbeat last run + running yes/no (section hidden if the request fails) | `GET /api/heartbeat/status` |
| L-sys-tokens | Token totals: input, output, cached, turns; per-call-type input/output | `GET /api/tokens` |

#### Not a user-facing surface

`ui/app/components/metrics/DerivedCard.tsx` is unused. Do not invent a page for it. `StatBar` is the chemistry readout on the Lab Chemistry page and must keep working.

---

## 2. Single IA (Option C)

### Product model

One shell: the existing `AppRoot` frame and `AppHeader` chrome. The main column is either the chat canvas or an instrumentation route. Same header, same scroll rules, same way back. The Mina wordmark and a **Chat** item both return to `/`.

Stop using “Lab” as a product name in the nav. Routes may keep the `/admin` prefix.

```
Header:  [Mina]  [status]                    [Scene] [Clear] [Tools]
Body:    [primary nav]  [ chat canvas  |  instrumentation route ]
```

Primary nav is **one list**, not a header mode plus a second sidebar. Wide (`sm+`): persistent sidebar. Narrow: the same list in a drawer (the Lab bottom bar and the hidden Chat\|Lab links both go away in RES-122). Below 640px today, Chat\|Lab is already hidden; the wordmark is the only reliable jump back to `/`. The new drawer is what makes every destination reachable on a phone.

### Primary nav

Order is conversation first, then state, then traces, then ops. Overview stays in the list so the dashboard does not disappear; it is no longer a separate app’s front door.

| Nav label | Route (unchanged) | Replaces |
|-----------|-------------------|----------|
| Chat | `/` | Header “Chat”. Default. |
| Overview | `/admin` | Lab “Overview”. |
| Chemistry | `/admin/neuro` | Lab “Chemistry”. Canonical chem editors. |
| Free time | `/admin/freetime` | Lab “Free time”. |
| Turn trace | `/admin/context` | Lab “Context”. Nav label only; route stays. |
| History | `/admin/history` | Lab “History”. |
| Events | `/admin/events` | Lab “Events”. |
| System | `/admin/system` | Lab “System”. |

`/admin/control` keeps redirecting to `/`.

Eight items is the same destination count as today’s Lab seven plus Chat. The cut is the **second** nav (header mode + Lab sidebar + Control’s three tabs + a modal), not the pages.

### Always visible (Chat home)

- Wordmark, status pill, primary nav (sidebar or a single menu button that opens the drawer).
- Message stream, including per-turn ThoughtStream. The mind stays **in the transcript**. It is not a nav destination.
- Composer: pics count, aspect, textarea, Send.
- Header actions that are conversation-scoped and cheap: **Scene** (today’s “Context” button — rename in the header so it does not collide with Turn trace), **Clear**, **Tools**.

Status pill keeps a one-word presence read. RES-122 should use `presenceLabel` (the Lab wording) plus the Chat overrides Thinking / Offline, so the richer Lab label is not lost when the two headers merge.

### Progressive disclosure

| Surface | Opens from | Holds | Pattern to reuse |
|---------|------------|-------|------------------|
| Scene dialog | Header **Scene** | C-scene-* only (`ChatContextModal`) | Existing modal |
| Tools sheet | Header **Tools** | Presets, advance hours, run heartbeat, reset chemistry, erase history | Same idea as today’s Control drawer / a shadcn sheet. Confirms stay on reset and erase |
| Presence sheet | Status pill | Sleep card, felt state, signals, one-line latest free time, links to Overview and Free time | Sheet. Not a third permanent column |
| Lightbox | Image in a bubble | C-lightbox | Existing |
| Instrumentation routes | Primary nav | Full Lab pages, unchanged internally in this epic’s IA | Main column, same shell |
| Chemistry editors, secretion queue, receptor table | Chemistry route | L-chem-* | Page, not the chat column |
| Turn-trace sections, copy, raw md | Turn trace route | L-turn-* | Page |
| Free-time session list and pillar dump | Free time route | L-ft-* | Page |
| History charts, event log, system health | Their routes | L-hist-*, L-ev-*, L-sys-* | Pages |

The permanent Control column (`C-control-desktop` / `C-control-toggle` as a third pane) is **retired in the target IA**. Its three tabs move:

- Presence → Presence sheet + Overview route
- Chemistry → Chemistry route (the sheet is not a second editor; see §3)
- Tools → Tools sheet

`mina-control-open` can die with that column (RES-122). Do not replace it with a remembered “Lab mode.”

### What is intentionally not merged

These pairs share words and must stay **two reaches**:

| Keep separate | Why |
|---------------|-----|
| Scene dialog (`/api/scene`) vs Turn trace (`/api/context`) | Scene is clothing, positions, fiction-now, timeline, plans, inject. Turn trace is the last pillar assembly: encoder, decoder table, RAG/KAG, system prompt, reply. |
| ThoughtStream vs Turn trace | Mind is per message in the thread (summary you can reopen). Turn trace is the latest full dump, with raw retrieval and copy-as-markdown. |
| Clear vs Erase | Clear empties the chat store view. Erase wipes transcript, scene, diary, RAG, relationship, and free-time sessions. |
| Free-time peek vs Free time page | Peek is the latest line. The page is the session list and the pillar/tool dump. |

---

## 3. Control ↔ Lab duplicates (RES-125)

Same facts, two UIs. RES-125 picks the surviving control and deletes the twin **without** dropping an action from §4.

**Outcome (implemented):**

- Sleep is one card (`SleepStatusCard`): compact on the Presence sheet, page-size on Overview. Both use `sleepStatusLines`. The sheet footer no longer repeats awake/sleeping.
- Felt state and signals are one readout (`FeltMetricList`): bars on the sheet, cards on Overview. Same six + six fields.
- Free-time peek lives only on the Presence sheet (`FreetimePeek`, up to 4 chips). Overview no longer peeks. The Free time page stays the session log.
- Chemistry route is the only editor. The union, including `substance_p`, `vasopressin`, and `crh` under Stress, is `ui/app/lib/chem-groups.ts`. No second slider list.
- Presets, advance, heartbeat, reset, and erase stay on the header Tools sheet. System keeps heartbeat status. Free-time empty copy points at that sheet.

The map of every former Control-tab / Lab-page action is [docs/res-125-action-map.md](../res-125-action-map.md). The table below is the problem this outcome closed.

| Topic | Control (`ControlPane.tsx`) | Lab | Note for RES-125 |
|-------|------------------------------|-----|------------------|
| Sleep / presence | Presence tab consciousness card + footer awake/sleeping. Chat header is coarser (Live/Sleeping) | Overview sleep card. Header uses `presenceLabel` + poll age | One sleep card. One status vocabulary. |
| Felt state + signals | Presence bars, 6 + 6 | Overview cards, same fields | One readout. Overview can be that readout at page size; the sheet can be the compact form. |
| Free time | Presence peek, 3 chips, link to `/admin/freetime` | Overview peek, 4 chips, same link. Full page is the real tool | Peek in one place (Presence sheet or Overview, not both plus the page). Page stays canonical for sessions, diary, copy. |
| Chemistry sliders | Five groups, Set, tooltip implication. Missing `substance_p` and `vasopressin`. `crh` under Other | Five groups, Save, `StatBar` implication text. Extra chemicals. `crh` under Stress. Secretion queue + receptor table **only here** | Chemistry route is the only editor. Do not keep a second slider list in a chat side panel. Any chat-side chem control, if kept at all, is a shortcut into this page — not a partial duplicate that hides two chemicals. |
| Presets, advance, heartbeat, reset, erase | Tools tab only | Not on Lab pages. Free-time empty state tells you to use Control → heartbeat. System shows heartbeat **status** only | These actions move to the Tools sheet. They are not Lab duplicates; they are Lab-adjacent and easy to orphan. System keeps the status readout. |
| “Open Lab…” links | Presence → Free time. Tools → `/admin` | Overview → Free time, Overview → Events. Sidebar “← Back to Chat” | In-shell nav replaces cross-app links. |
| Events | None in Control | Overview strip of 8 + full Events page | Strip can stay on Overview. Not a Control feature. |
| Turn mind vs assembly | ThoughtStream on the bubble; scene modal | Turn trace page; free-time pillar sections mirror the same encoder/decoder/assembly/insula/hippocampus/PFC/system blocks | Per RES-121 these stay. RES-125 should not collapse ThoughtStream into Turn trace. Free-time’s pillar sections are a per-session copy of the turn-trace shape; that is a page-internal duplicate, optional later, not a Control pane issue. |

Destructive pair to keep distinct in copy and in confirms:

- **Reset chemistry** — baseline chem only; chat and memory stay.
- **Erase conversation** — transcript, scene, diary, RAG, relationship, free-time sessions.
- **Clear** — UI transcript / chat store only.

---

## 4. Reachability checklist (feeds RES-124)

Every inventory id remains reachable under the IA in §2. RES-122/125 may change the trigger; they may not drop the row.

| ID | Proposed reach |
|----|----------------|
| C-status | Header status pill (presence label + Thinking / Offline) |
| C-context-open, C-scene-refresh, C-scene-live, C-scene-timeline, C-scene-plans, C-scene-inject, C-scene-jump | Header **Scene** → existing modal |
| C-clear | Header **Clear** |
| C-control-toggle, C-control-desktop, C-control-drawer | Retired as a pane. Contents redistributed below. The open/close preference does not need a replacement |
| C-empty, C-send, C-edit, C-redo, C-error, C-persist, C-erase-event | Chat home, unchanged |
| C-img-count, C-img-aspect, C-img-render, C-img-pending, C-img-fail, C-lightbox | Composer + bubbles + lightbox |
| C-mind-live, C-mind-archive, C-mind-rail, C-mind-chem, C-mind-feel, C-mind-memory, C-mind-situate, C-mind-decide, C-mind-silence | Inline ThoughtStream on Chat |
| C-pres-sleep, C-pres-felt, C-pres-signals | Presence sheet (compact) and Overview (page). Shared components; see [action map](../res-125-action-map.md) |
| C-pres-ft | Presence sheet peek only, plus the Free time page for sessions. Overview does not peek |
| C-chem-mono, C-chem-bond, C-chem-stress, C-chem-sleep, C-chem-other | Chemistry route. Union of chemicals must include Control’s set |
| C-preset, C-advance, C-heartbeat, C-reset, C-erase | Header **Tools** sheet, with the same confirms |
| C-lab-link | Primary nav (no cross-app link required) |
| L-ov-title, L-ov-sleep, L-ov-felt, L-ov-signals, L-ov-events | Overview route |
| L-ov-ft | Moved to the Presence sheet peek (one peek). Free time page remains the session log |
| L-chem-mono, L-chem-bond, L-chem-stress, L-chem-sleep, L-chem-other, L-chem-queue, L-chem-receptors | Chemistry route. Union must include `substance_p`, `vasopressin`, secretion queue, receptors |
| L-turn-live, L-turn-refresh, L-turn-copy, L-turn-raw, L-turn-meta, L-turn-msg, L-turn-enc, L-turn-dec, L-turn-asm, L-turn-ins, L-turn-hip, L-turn-pfc, L-turn-sys, L-turn-reply, L-turn-empty | Turn trace route (`/admin/context`) |
| L-ft-live, L-ft-refresh, L-ft-copy, L-ft-raw, L-ft-list, L-ft-meta, L-ft-msg, L-ft-tools, L-ft-reply, L-ft-enc, L-ft-dec, L-ft-asm, L-ft-ins, L-ft-hip, L-ft-pfc, L-ft-sys, L-ft-empty | Free time route |
| L-hist-range, L-hist-groups, L-hist-chart | History route |
| L-ev-filter, L-ev-auto, L-ev-row, L-ev-expand, L-ev-more | Events route |
| L-sys-build, L-sys-bill, L-sys-hb, L-sys-tokens | System route |
| `/admin/control` redirect | Keep |

Mobile acceptance for RES-124: every primary-nav row is reachable below 640px from the drawer, and Chat is reachable from an instrumentation route without relying on the wordmark alone.

---

## 5. Out of scope for follow-on tickets to ignore

- Visual polish, density, and token cleanup (RES-123).
- Building the sidebar/drawer shell (RES-122). This ADR names the regions; it does not spec spacing, type, or shadcn component choice beyond “sidebar / sheet / existing modal.”
- Removing duplicate chem sliders, presence cards, or free-time peeks (RES-125). Done. See [docs/res-125-action-map.md](../res-125-action-map.md).
- Backend, API, or route renames. `/admin/*` stays.
- New features. No new instrumentation. `DerivedCard` stays unused.
