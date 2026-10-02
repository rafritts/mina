"""RES-124 — static no-drop checks for the unified workspace.

Reads the UI sources. Does not boot Next or the sim. Fails if a §4
destination, header action, Tools action, or chemistry-union chemical
disappears from the tree.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui" / "app"


def _text(rel: str) -> str:
    path = UI / rel
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_primary_nav_is_chat_plus_lab_routes() -> None:
    src = _text("components/shell/primary-nav.ts")
    hrefs = re.findall(r"href:\s*'([^']+)'", src)
    labels = re.findall(r"label:\s*'([^']+)'", src)
    assert list(zip(labels, hrefs)) == [
        ("Chat", "/"),
        ("Overview", "/admin"),
        ("Chemistry", "/admin/neuro"),
        ("Free time", "/admin/freetime"),
        ("Turn trace", "/admin/context"),
        ("History", "/admin/history"),
        ("Events", "/admin/events"),
        ("System", "/admin/system"),
    ]


def test_mobile_drawer_includes_the_same_nav_including_chat() -> None:
    css = (UI / "globals.css").read_text(encoding="utf-8")
    assert ".nav-menu-btn" in css
    assert re.search(
        r"\.nav-menu-btn\s*\{[^}]*display:\s*inline-flex",
        css,
    )
    assert re.search(
        r"@media \(min-width:\s*640px\)\s*\{[^}]*\.nav-menu-btn\s*\{[^}]*display:\s*none",
        css,
        re.S,
    )
    assert re.search(
        r"\.primary-nav\s*\{[^}]*display:\s*none",
        css,
    )
    shell = _text("components/shell/WorkspaceShell.tsx")
    assert 'className="nav-menu-btn"' in shell
    assert 'className="nav-drawer"' in shell
    assert shell.count("<PrimaryNav") == 2
    drawer = shell.split('className="nav-drawer"', 1)[1]
    assert "<PrimaryNav" in drawer


def test_header_scene_clear_tools_and_presence() -> None:
    shell = _text("components/shell/WorkspaceShell.tsx")
    for label in ("Scene", "Clear", "Tools"):
        assert f">{label}<" in shell or f"\n        {label}\n" in shell
    assert "ChatContextModal" in shell
    assert "PresenceSheet" in shell
    assert "ToolsSheet" in shell
    assert "setPresenceOpen(true)" in shell
    assert "presenceLabel" in shell
    assert "'Thinking'" in shell
    assert "'Offline'" in shell


def test_chat_send_edit_redo_images_mind_persist() -> None:
    chat = _text("components/ChatApp.tsx")
    for needle in (
        "Say something real.",
        "const send = ",
        "const handleRedo = ",
        "const handleEdit = ",
        "const clearView = ",
        "mina:erase-chat",
        "mina-chat-messages",
        "mina-chat-prefs",
        "ImageCountSelector",
        "AspectRatioSlider",
        "ThoughtStream",
        "function PhotoPending",
        "Image failed to load",
        "Developing photo…",
        "image_count:",
        "image_aspect:",
        "Pipeline starting…",
        "Enter to send",
        "<Lightbox",
    ):
        assert needle in chat, needle
    assert "disabled={sending || imageCount === 0}" in chat


def test_thoughtstream_sections_and_silence() -> None:
    mind = _text("components/ThoughtStream.tsx")
    for label in ("Sense", "Chem", "Feel", "Memory", "Situate", "Decide", "Speak"):
        assert f"label: '{label}'" in mind
    for title in (
        "Chem · appraisal",
        "Insula · felt state",
        "Memory · what surfaces",
        "Hippocampus · situation",
        "PFC · internal monologue",
    ):
        assert title in mind
    assert "Chose silence" in mind
    assert ".slice(0, 5)" in mind


def test_scene_modal_sections() -> None:
    modal = _text("components/ChatContextModal.tsx")
    for label in ("Live Scene", "Timeline", "Plans", "What she gets"):
        assert label in modal
    assert "Refresh" in modal
    assert "/api/scene" in modal
    assert "mina-ctx-" in modal
    assert "Escape" in modal
    assert "Fiction now" in modal
    assert "Clothing" in modal
    assert "Positions" in modal


def test_tools_sheet_actions_and_confirms() -> None:
    tools = _text("components/shell/ToolsSheet.tsx")
    assert "PRESETS" in tools
    assert "Run freetime heartbeat" in tools
    assert "Reset chemistry to baseline" in tools
    assert "Keeps chat & memory." in tools
    assert "Erase conversation history" in tools
    assert "free-time sessions" in tools
    assert "mina:erase-chat" in tools
    assert "/api/state/advance" in tools
    assert "min={0.25}" in tools and "max={168}" in tools and "step={0.25}" in tools
    assert 'href="/admin' not in tools


def test_presence_sheet_and_single_freetime_peek() -> None:
    presence = _text("components/shell/PresenceSheet.tsx")
    assert "SleepStatusCard" in presence
    assert 'density="compact"' in presence
    assert "FeltMetricList" in presence
    assert "SECOND_ORDER" in presence
    assert "THIRD_ORDER" in presence
    assert "FreetimePeek" in presence
    peek = _text("components/presence/FreetimePeek.tsx")
    assert 'href="/admin/freetime"' in peek
    assert "No free-time sessions yet" in peek
    assert "CHIP_LIMIT = 4" in peek
    overview = _text("admin/page.tsx")
    assert "FreetimePeek" not in overview
    assert "presenceLabel" in overview
    assert 'density="page"' in overview
    assert "/api/events?limit=8" in overview
    assert 'href="/admin/events"' in overview


def test_chemistry_union_queue_and_receptors() -> None:
    groups = _text("lib/chem-groups.ts")
    required = [
        "dopamine",
        "serotonin",
        "norepinephrine",
        "oxytocin",
        "endorphins",
        "cortisol",
        "epinephrine",
        "crh",
        "adenosine",
        "melatonin",
        "orexin",
        "anandamide",
        "ghrelin",
        "substance_p",
        "vasopressin",
    ]
    for name in required:
        assert f"'{name}'" in groups
    stress = re.search(r"label: 'Stress'.*?chemicals: \[([^\]]+)\]", groups, re.S)
    assert stress and "'crh'" in stress.group(1)
    neuro = _text("admin/neuro/page.tsx")
    assert "CHEM_EDITOR_GROUPS" in neuro
    assert "Secretion queue" in neuro
    assert "Receptor sensitivities" in neuro
    assert "StatBar" in neuro


def test_turn_trace_freetime_history_events_system() -> None:
    ctx = _text("admin/context/page.tsx")
    for label in (
        "User message",
        "Encoder (amygdala)",
        "Decoder (chemistry)",
        "Context assembly",
        "Insula (emotion)",
        "Hippocampus (situation)",
        "PFC (strategy)",
        "System prompt (Mina sees)",
        "Reply",
    ):
        assert label in ctx
    assert "No assembly yet — send a chat message first." in ctx
    assert "(silence)" in ctx
    assert "4000" in ctx
    assert "/api/context" in ctx

    ft = _text("admin/freetime/page.tsx")
    for label in (
        "Synthetic input",
        "Tools & diary",
        "Reply / note",
        "record_diary",
    ):
        assert label in ft
    assert "fetchFreetime(50)" in ft
    assert "8000" in ft
    assert "Run freetime heartbeat" in ft

    hist = _text("admin/history/page.tsx")
    assert "{ label: '1h'" in hist
    assert "{ label: '6h'" in hist
    assert "{ label: '24h'" in hist
    assert "{ label: '7d'" in hist
    assert "useState(6)" in hist
    assert "No history samples yet" in hist
    assert "LineChart" in hist

    events = _text("admin/events/page.tsx")
    assert "['all', 'activity', 'tool', 'stimulus', 'response']" in events
    assert "Auto-refresh" in events
    assert "5000" in events
    assert "Load more" in events
    assert "load(500)" in events
    assert ".slice(0, 5)" in events

    system = _text("admin/system/page.tsx")
    assert "BUILD_INFO" in system
    assert "/api/billing" in system
    assert "/api/heartbeat/status" in system
    assert "/api/tokens" in system
    assert "billingPct > 80" in system
    assert "billingPct > 60" in system


def test_control_bookmark_redirects_home() -> None:
    page = _text("admin/control/page.tsx")
    assert "redirect('/')" in page


def test_presets_cover_the_inventory() -> None:
    presets = _text("lib/presets.ts")
    for name in (
        "Baseline",
        "Euphoria",
        "Flow",
        "Loved",
        "Anxious",
        "Despair",
        "Lonely",
        "Tender",
        "Irritable",
        "Sleepy",
    ):
        assert f"name: '{name}'" in presets
