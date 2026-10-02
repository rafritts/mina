# RES-124 — No-drop acceptance

**Status:** Checklist complete on `master` `80c33be` (RES-121–125 merged). **Open gaps: none.** No reachability fix was required.

**Tickets:** [RES-124](https://linear.app/restlessapi/issue/RES-124) (this checklist), parent [RES-120](https://linear.app/restlessapi/issue/RES-120).

**Sources:** [ADR 0001](adr/0001-unified-workspace-ia.md) §1 inventory and §4 reachability, [RES-125 action map](res-125-action-map.md), current shell under `ui/app/components/shell/`, Chat at `ui/app/components/ChatApp.tsx`, Lab routes under `ui/app/admin/`.

**How to read status**

| Status | Meaning |
|--------|---------|
| Reachable (code-verified) | The §4 trigger is in the tree. A person can open it from the cited component or route. |
| Needs live Mini click | Path exists in code but was not exercised against a running sim in this pass. |
| Gap | The capability is gone and was not redistributed. Must be fixed in the same PR. |

This pass is source verification, not a live Mini session. Every row below is **Reachable (code-verified)**. A Mini click-through after merge is still the product check in the ticket; it is not an open gap.

Retired rows (`C-control-*`, `L-ov-ft`) stay on the list. §4 moves them on purpose. Their contents are cited at the new home.

`tests/test_res124_reachability.py` asserts the routes, header actions, Tools actions, chemistry union, and mobile drawer link. It does not replace this table.

---

## Mobile

Below 640px the persistent sidebar is hidden and the header menu button is shown (`ui/app/globals.css`: `.primary-nav` is `display: none` until `min-width: 640px`; `.nav-menu-btn` is `inline-flex` until that breakpoint, then `display: none`).

The button opens the drawer in `WorkspaceShell` (`nav-drawer`). The drawer renders the same `PrimaryNav` as the sidebar. `PRIMARY_NAV` in `ui/app/components/shell/primary-nav.ts` starts with **Chat** → `/`, then Overview, Chemistry, Free time, Turn trace, History, Events, System.

From an instrumentation route, Chat is a drawer row. The wordmark (`AppHeader` `Link` to `/`) is a second way home, not the only one. At `sm+` the same Chat row is in the persistent sidebar.

---

## Chat home — `/`

Mounted by `ui/app/page.tsx` → `ChatApp`, inside `WorkspaceShell` (`ui/app/layout.tsx`).

### Shell

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-status | Header status pill (presence label + Thinking / Offline) | `WorkspaceShell` status block: override `thinking` → Thinking, `offline` → Offline, else `presenceLabel(state)` (Sleeping, Anxious, Elevated, Focused, Warm, Low, Depleted, Present). `ChatApp` calls `setStatusOverride` while sending or disconnected. Pill is `AppHeader` `status-pill`; click opens Presence. | Reachable (code-verified) |
| C-context-open | Header **Scene** → existing modal | `WorkspaceShell` header button “Scene” sets `sceneOpen` and mounts `ChatContextModal`. | Reachable (code-verified) |
| C-clear | Header **Clear** | Header button “Clear” → `onClear`. On `/`, `ChatApp.clearView` is registered via `setClearHandler` (empties the transcript, `flushRemoteStore([])`, does not call `/api/conversation/erase`). Off Chat, the same button calls `clearRemoteTranscript`. | Reachable (code-verified) |
| C-control-toggle | Retired as a pane. Contents redistributed. Preference does not need a replacement. | No `ControlPane`, no `mina-control-open`. Presence is the status-pill sheet; chemistry is `/admin/neuro`; presets / advance / heartbeat / reset / erase are the Tools sheet. | Reachable (code-verified) |
| C-control-desktop | Same retirement. | No `lg` Control column. Instrumentation uses `shell-main`. | Reachable (code-verified) |
| C-control-drawer | Same retirement. | No `control-drawer-backdrop`. Narrow overlays are the nav drawer, Presence sheet, and Tools sheet. | Reachable (code-verified) |

### Message stream

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-empty | Chat home, unchanged | `ChatApp` empty block: “Say something real.” when hydrated and `messages.length === 0`. | Reachable (code-verified) |
| C-send | Chat home, unchanged | `send` / `submitTurn`. Enter sends, Shift+Enter newline (`onKeyDown`). Send button and textarea `disabled` while `sending`. Body sends `image_count` and `image_aspect`. | Reachable (code-verified) |
| C-edit | Chat home, unchanged | `UserMessage` + `handleEdit`. Edit control only when `m.id === lastUserMessageId`. Resubmits with `redo: true` and `rewindMessage`. | Reachable (code-verified) |
| C-redo | Chat home, unchanged | Assistant bubble “Redo” → `handleRedo` → `submitTurn(userText, { redo: true })` from the preceding user text. | Reachable (code-verified) |
| C-error | Chat home, unchanged | `error` state renders `alert alert-error`. Set from stream `error` and failed send. | Reachable (code-verified) |
| C-persist | Chat home, unchanged | `flushRemoteStore` / `pullChatStore` via `ui/app/lib/chat-store-api.ts`. One-time migrate of `mina-chat-messages` and `mina-chat-prefs`. | Reachable (code-verified) |
| C-erase-event | Chat home, unchanged | `ChatApp` listens for `mina:erase-chat` and clears the local transcript. `ToolsSheet` erase dispatches that event after `POST /api/conversation/erase`. | Reachable (code-verified) |

### Images

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-img-count | Composer | `ImageCountSelector` on the composer. Options Auto, 0, 1–5 in `ui/app/lib/image-count.ts`. Stored with the chat store; sent as `image_count`. | Reachable (code-verified) |
| C-img-aspect | Composer | `AspectRatioSlider`. Landscape / square / portrait in `ui/app/lib/image-aspect.ts`. `disabled` when sending or count is 0. Sent as `image_aspect`. | Reachable (code-verified) |
| C-img-render | Bubbles | `splitMessageMedia` pulls `/images/…` and `/api/generate/…` markdown (and bare `/images/` URLs) into `ChatImage` with caption. | Reachable (code-verified) |
| C-img-pending | Bubbles | `PhotoPending` when `m.imagePending` (“Developing photo…”). | Reachable (code-verified) |
| C-img-fail | Bubbles | `ChatImage` failed-load path: `alert alert-error` “Image failed to load”. | Reachable (code-verified) |
| C-lightbox | Image in a bubble | `Lightbox`: prev/next, dot strip (`lightbox-dots`) to jump, open original, download, close, Escape. | Reachable (code-verified) |

### ThoughtStream

Inline on the transcript (`ThoughtStream`). Live while `sending`; archived minds are collapsible, newest open (`defaultOpen` on the last assistant mind).

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-mind-live | Inline ThoughtStream | `ThoughtStream` `live` while sending. Empty pipeline shell in `ChatApp`: “Pipeline starting…”. `live` forces the panel open; typewriter runs when `enabled={live}`. | Reachable (code-verified) |
| C-mind-archive | Inline ThoughtStream | `collapsible` archived row, label “Mind”, `mindSummary` (affect · approach · tone). Show/Hide. | Reachable (code-verified) |
| C-mind-rail | Inline ThoughtStream | `STAGES`: Sense, Chem, Feel, Memory, Situate, Decide, Speak (`mind-stage-rail`). | Reachable (code-verified) |
| C-mind-chem | Inline ThoughtStream | `MindBody` “Chem · appraisal → Class‑1”: flags, encoder axes, applied deltas (nM), quiet-turn copy. | Reachable (code-verified) |
| C-mind-feel | Inline ThoughtStream | “Insula · felt state”: affect, trend, availability, summary, somatic, drive. | Reachable (code-verified) |
| C-mind-memory | Inline ThoughtStream | “Memory · what surfaces”, `slice(0, 5)`, KAG vs recall. | Reachable (code-verified) |
| C-mind-situate | Inline ThoughtStream | “Hippocampus · situation”: social context, urgency, summary, notable. | Reachable (code-verified) |
| C-mind-decide | Inline ThoughtStream | “PFC · internal monologue”: reaction, approach, tone, lead-with. | Reachable (code-verified) |
| C-mind-silence | Inline ThoughtStream | Completed skipped turn sets the live/done head to “Chose silence” when `mind.skipped`. | Reachable (code-verified) |

### Scene dialog

`ChatContextModal`. Header **Scene**. Escape and backdrop close. Loads `GET /api/scene`. Not the Turn trace page.

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-scene-refresh | Header Scene | Header “Refresh” calls `load`. | Reachable (code-verified) |
| C-scene-live | Header Scene | Section `mina-ctx-scene`: fiction now, clothing cards, position cards, empty hint. | Reachable (code-verified) |
| C-scene-timeline | Header Scene | Section `mina-ctx-timeline`. Last row marked “Latest”. | Reachable (code-verified) |
| C-scene-plans | Header Scene | Section `mina-ctx-plans`. | Reachable (code-verified) |
| C-scene-inject | Header Scene | Section `mina-ctx-inject`: system prompt or inject, Copy. | Reachable (code-verified) |
| C-scene-jump | Header Scene | `Segmented` over `SECTIONS` (Live Scene, Timeline, Plans, What she gets) scrolls to `mina-ctx-${id}`. | Reachable (code-verified) |

### Presence sheet

Status pill → `PresenceSheet`. Compact sleep, felt, signals. Free-time peek only here.

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-pres-sleep | Presence sheet (compact) and Overview (page) | `SleepStatusCard` `density="compact"` in `PresenceSheet`; `density="page"` on Overview. Copy from `sleepStatusLines`. Pill Sleeping / Awake. | Reachable (code-verified) |
| C-pres-felt | Presence sheet bars and Overview cards | `FeltMetricList` `variant="bar"` with `SECOND_ORDER` (energy, mood, warmth, clarity, arousal, hedonic). Overview uses `variant="card"`. | Reachable (code-verified) |
| C-pres-signals | Same component, two densities | `FeltMetricList` with `THIRD_ORDER` (anxiety, low mood, boredom, loneliness, flow, distress). | Reachable (code-verified) |
| C-pres-ft | Presence sheet peek only, plus the Free time page | `FreetimePeek` in `PresenceSheet` only. Up to 4 chips, relative time (`title` = clock), two-line body, empty “No free-time sessions yet.” Link “Open Free time →” → `/admin/freetime`. Poll 15s. Overview does not import it. | Reachable (code-verified) |

### Chemistry (Control’s groups)

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-chem-mono | Chemistry route. Union includes Control’s set. | `/admin/neuro` → `CHEM_EDITOR_GROUPS` “Monoamines”: dopamine, serotonin, norepinephrine. `StatBar` + range + Save (`PATCH /api/state`). | Reachable (code-verified) |
| C-chem-bond | Chemistry route | “Bonding & social”: oxytocin, endorphins. | Reachable (code-verified) |
| C-chem-stress | Chemistry route | “Stress”: cortisol, epinephrine, **crh** (Control had listed crh under Other). | Reachable (code-verified) |
| C-chem-sleep | Chemistry route | “Sleep & clock”: adenosine, melatonin, orexin. | Reachable (code-verified) |
| C-chem-other | Chemistry route | “Other peptides”: anandamide, ghrelin, plus substance_p and vasopressin. | Reachable (code-verified) |

### Tools sheet

Header **Tools** → `ToolsSheet`. Confirms stay on reset and erase.

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| C-preset | Header Tools, same confirms | `PRESETS` grid (`ui/app/lib/presets.ts`): Baseline, Euphoria, Flow, Loved, Anxious, Despair, Lonely, Tender, Irritable, Sleepy. `PATCH /api/state`. | Reachable (code-verified) |
| C-advance | Header Tools | Hours input `min={0.25}` `max={168}` `step={0.25}`, default `"1"`. `POST /api/state/advance`. | Reachable (code-verified) |
| C-heartbeat | Header Tools | Button “Run freetime heartbeat”. `POST /api/heartbeat`. System keeps status only. | Reachable (code-verified) |
| C-reset | Header Tools, confirm keeps chat & memory | Confirm: “Reset chemistry to baseline? Keeps chat & memory.” `POST /api/state/reset`. | Reachable (code-verified) |
| C-erase | Header Tools, confirm lists the wipe, then `mina:erase-chat` | Confirm names transcript, scene, diary, RAG, who you are to her, free-time sessions. `POST /api/conversation/erase`, then `mina:erase-chat`. | Reachable (code-verified) |
| C-lab-link | Primary nav. No cross-app link required. | `PRIMARY_NAV` lists every instrumentation route. Tools sheet has no “Open Lab” link. | Reachable (code-verified) |

---

## Lab routes

Layout is `ui/app/admin/layout.tsx` (`shell-scroll` only). Nav is the shared primary list, not a second sidebar.

| Nav label | Route |
|-----------|--------|
| Chat | `/` |
| Overview | `/admin` |
| Chemistry | `/admin/neuro` |
| Free time | `/admin/freetime` |
| Turn trace | `/admin/context` |
| History | `/admin/history` |
| Events | `/admin/events` |
| System | `/admin/system` |

`/admin/control` → `redirect('/')` in `ui/app/admin/control/page.tsx`.

### Overview — `/admin`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-ov-title | Overview | `h1` = `presenceLabel(state)`. | Reachable (code-verified) |
| L-ov-sleep | Overview | `SleepStatusCard` `density="page"`. | Reachable (code-verified) |
| L-ov-felt | Overview cards | `FeltMetricList` `variant="card"` + `SECOND_ORDER`. | Reachable (code-verified) |
| L-ov-signals | Overview cards | `FeltMetricList` `variant="card"` + `THIRD_ORDER`. | Reachable (code-verified) |
| L-ov-events | Overview | `GET /api/events?limit=8`. Type chip, preview, relative time. “View all” → `/admin/events`. | Reachable (code-verified) |
| L-ov-ft | Moved to the Presence sheet peek. Free time page remains the session log. | Overview copy points at the status pill. Peek component is `FreetimePeek` on the Presence sheet (`C-pres-ft`). Session log is `/admin/freetime`. | Reachable (code-verified) |

### Chemistry — `/admin/neuro`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-chem-mono | Chemistry route | Same `CHEM_EDITOR_GROUPS` Monoamines row as C-chem-mono. | Reachable (code-verified) |
| L-chem-bond | Chemistry route | Bonding & social. | Reachable (code-verified) |
| L-chem-stress | Chemistry route | Stress, including crh. | Reachable (code-verified) |
| L-chem-sleep | Chemistry route | Sleep & clock. | Reachable (code-verified) |
| L-chem-other | Chemistry route | Other peptides, including substance_p and vasopressin. Missing snapshot keys still render from `DISPLAY_RANGES`. | Reachable (code-verified) |
| L-chem-queue | Chemistry route | “Secretion queue” table: chemical, remaining, rate/hr. Empty state when `secretion_queue` is empty. | Reachable (code-verified) |
| L-chem-receptors | Chemistry route | “Receptor sensitivities” table over `state.receptor_sensitivity`. | Reachable (code-verified) |

`ui/app/components/metrics/StatBar.tsx` is the readout (implication text, gap, normalized /10). `DerivedCard` is still unused and has no page.

### Turn trace — `/admin/context`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-turn-live | Turn trace | Live/paused toggle. Interval 4s while `autoRefresh`. | Reachable (code-verified) |
| L-turn-refresh | Turn trace | “Refresh” reloads `/api/context` and `/api/context/text`. | Reachable (code-verified) |
| L-turn-copy | Turn trace | “Copy md” and “Copy json”. | Reachable (code-verified) |
| L-turn-raw | Turn trace | “Raw md” / “Sections” toggles `showRaw`. | Reachable (code-verified) |
| L-turn-meta | Turn trace | Timestamp, `relativeAge`, source, username, “skipped reply” when `record.skipped`. | Reachable (code-verified) |
| L-turn-msg | Turn trace | Section “User message”. | Reachable (code-verified) |
| L-turn-enc | Turn trace | “Encoder (amygdala)” plus `relationship_modifier`. | Reachable (code-verified) |
| L-turn-dec | Turn trace | Decoder table: norm, set, gap, rate, plus Big 5. | Reachable (code-verified) |
| L-turn-asm | Turn trace | “Context assembly”: window, RAG, KAG, raw retrieval (sliding + episodic). | Reachable (code-verified) |
| L-turn-ins | Turn trace | “Insula (emotion)”. | Reachable (code-verified) |
| L-turn-hip | Turn trace | “Hippocampus (situation)”. | Reachable (code-verified) |
| L-turn-pfc | Turn trace | “PFC (strategy)”. | Reachable (code-verified) |
| L-turn-sys | Turn trace | “System prompt (Mina sees)”. | Reachable (code-verified) |
| L-turn-reply | Turn trace | “Reply”, or `(silence)` when `record.skipped`. | Reachable (code-verified) |
| L-turn-empty | Turn trace | 404 sets “No assembly yet — send a chat message first.” Shown as the empty notice detail (`offlineDetail`). | Reachable (code-verified) |

### Free time — `/admin/freetime`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-ft-live | Free time | Live/paused toggle. Interval 8s. | Reachable (code-verified) |
| L-ft-refresh | Free time | “Refresh” reloads list, detail, and markdown. | Reachable (code-verified) |
| L-ft-copy | Free time | “Copy md” and “Copy json”. | Reachable (code-verified) |
| L-ft-raw | Free time | “Raw md” / “Sections”. | Reachable (code-verified) |
| L-ft-list | Free time | `fetchFreetime(50)`. Relative time, duration, up to 3 chips, two-line body. Click sets `selectedTs` and loads detail. | Reachable (code-verified) |
| L-ft-meta | Free time | Clock, relative time, duration, tool labels, “pillars” or “no pillar dump”. | Reachable (code-verified) |
| L-ft-msg | Free time | Section “Synthetic input”. | Reachable (code-verified) |
| L-ft-tools | Free time | “Tools & diary”. `record_diary` prose, other tool args, result. Badge = tool count. | Reachable (code-verified) |
| L-ft-reply | Free time | “Reply / note”. | Reachable (code-verified) |
| L-ft-enc | Free time | Encoder + relationship modifier, or the no-pillar-dump line. | Reachable (code-verified) |
| L-ft-dec | Free time | `DecoderTable` (norm, set, gap, rate) + Big 5. | Reachable (code-verified) |
| L-ft-asm | Free time | Window, RAG, KAG, raw retrieval. | Reachable (code-verified) |
| L-ft-ins | Free time | “Insula (emotion)”. | Reachable (code-verified) |
| L-ft-hip | Free time | “Hippocampus (situation)”. | Reachable (code-verified) |
| L-ft-pfc | Free time | “PFC (strategy)”. | Reachable (code-verified) |
| L-ft-sys | Free time | “System prompt (Mina sees)”. | Reachable (code-verified) |
| L-ft-empty | Free time | Empty list and the footer point at header Tools → Run freetime heartbeat, and say reset and erase live on that sheet. | Reachable (code-verified) |

### History — `/admin/history`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-hist-range | History | `TIME_RANGES`: 1h, 6h, 24h, 7d. Default `hours` state is 6. `useHistoryPoller`. | Reachable (code-verified) |
| L-hist-groups | History | `CHART_GROUPS`: Monoamines (dopamine, serotonin, norepinephrine), Stress (cortisol, norepinephrine), Derived (energy, hedonic tone, mood valence, anxiety), Social (oxytocin, social warmth). | Reachable (code-verified) |
| L-hist-chart | History | Recharts `LineChart` with time axis, tooltip, legend. Empty: “No history samples yet”. | Reachable (code-verified) |

### Events — `/admin/events`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-ev-filter | Events | `TYPE_FILTERS`: all, activity, tool, stimulus, response. | Reachable (code-verified) |
| L-ev-auto | Events | “Auto-refresh” checkbox, default on, interval 5s, `load(100)`. | Reachable (code-verified) |
| L-ev-row | Events | Type chip, `eventText` (preview / result / tool), up to 5 delta chips, relative time with absolute `title`. | Reachable (code-verified) |
| L-ev-expand | Events | Row click toggles `expanded` and shows the full text. | Reachable (code-verified) |
| L-ev-more | Events | “Load more” calls `load(500)`. | Reachable (code-verified) |

### System — `/admin/system`

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| L-sys-build | System | Build id, git, built-at from `BUILD_INFO` (`ui/app/lib/build-info.ts`). | Reachable (code-verified) |
| L-sys-bill | System | `GET /api/billing`. Used/cap bar, percent, remaining. Fill uses warning above 60% and danger above 80%. | Reachable (code-verified) |
| L-sys-hb | System | `GET /api/heartbeat/status`. Section renders only when the request returns. Last run + running yes/no. Run action stays on Tools. | Reachable (code-verified) |
| L-sys-tokens | System | `GET /api/tokens`. Totals: input, output, cached, turns. Per-call-type input/output table. | Reachable (code-verified) |

### Bookmark

| ID | Proposed reach | Code proof | Status |
|----|----------------|------------|--------|
| `/admin/control` redirect | Keep | `ui/app/admin/control/page.tsx` calls `redirect('/')`. | Reachable (code-verified) |

---

## Pairs that stay two reaches

| Pair | Still separate |
|------|----------------|
| Scene vs Turn trace | `ChatContextModal` (`/api/scene`) vs `/admin/context` (`/api/context`). |
| ThoughtStream vs Turn trace | Per-message `ThoughtStream` vs the latest full dump. |
| Clear vs Erase vs Reset | Header Clear flushes the chat store view. Tools Erase calls `/api/conversation/erase`. Tools Reset calls `/api/state/reset` and keeps chat and memory. |
| Free-time peek vs Free time page | `FreetimePeek` on the Presence sheet vs `/admin/freetime`. |

---

## Result

Every C-* and L-* inventory id in ADR §1 is reachable under the §4 map. No row is a Gap. No UI behavior was changed in this pass.
