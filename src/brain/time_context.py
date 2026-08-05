"""
Host wall-clock injection for Mina turns (Kaiya-style Local time / Clock period).

The sim's circadian chemistry (melatonin, cortisol, orexin) already runs on
local hour. This module makes the same clock legible to pillars and mouth so
felt state and replies can align with body time — without inventing fiction
scene_time from the wall clock.
"""
from __future__ import annotations

import time
from typing import Literal

DayPeriod = Literal["MORNING", "DAYTIME", "EVENING", "NIGHTTIME"]

# Same minute bands as Kaiya turn-prompt dayPeriod():
# MORNING 08:01–12:00, DAYTIME 12:01–20:00, EVENING 20:01–23:30, NIGHTTIME 23:31–08:00.
def day_period(now: float | None = None) -> DayPeriod:
    lt = time.localtime(now if now is not None else time.time())
    m = lt.tm_hour * 60 + lt.tm_min
    if m >= 8 * 60 + 1 and m <= 12 * 60:
        return "MORNING"
    if m >= 12 * 60 + 1 and m <= 20 * 60:
        return "DAYTIME"
    if m >= 20 * 60 + 1 and m <= 23 * 60 + 30:
        return "EVENING"
    return "NIGHTTIME"


def format_local_time(now: float | None = None) -> str:
    """Human local time, e.g. 'Tuesday, August 4, 2026, 3:45 PM'."""
    return time.strftime("%A, %B %-d, %Y, %-I:%M %p", time.localtime(now if now is not None else time.time()))


def _idle_line(last_activity_ts: float | None, now: float) -> str | None:
    if last_activity_ts is None or last_activity_ts <= 0:
        return None
    idle = now - last_activity_ts
    if idle <= 90:
        return "Ongoing conversation"
    if idle < 3600:
        return f"Last activity: {int(idle / 60)} minutes ago"
    if idle < 86400:
        hours = idle / 3600
        return f"Last activity: {hours:.1f} hours ago"
    return f"Last activity: {int(idle / 86400)} days ago"


def format_host_time_block(
    *,
    last_activity_ts: float | None = None,
    now: float | None = None,
    for_mouth: bool = True,
) -> str:
    """
    Kaiya-style host clock block for system / pillar prompts.

    for_mouth=True adds the wall-clock vs fiction-time note (mouth re-authors scene).
    """
    t = time.time() if now is None else now
    local = format_local_time(t)
    period = day_period(t)
    lines = [
        "[Turn context]",
        f"Local time: {local}. Clock period: {period}.",
    ]
    idle = _idle_line(last_activity_ts, t)
    if idle:
        lines.append(idle)
    if for_mouth:
        lines.append(
            "Wall clock is ambient reality — your circadian chemistry "
            "(melatonin, cortisol, orexin, adenosine/sleep pressure) runs on this. "
            "Soft fiction scene_time / timeline / plans (live scene) are narrative "
            "coherence only: they do not replace this clock for real body-time, and "
            "this clock does not reset fiction time when the story already jumped "
            "(sleep, skip, tomorrow-is-now)."
        )
    else:
        lines.append(
            "Wall clock is ambient reality for circadian chemistry interpretation. "
            "Do not invent a different hour."
        )
    return "\n".join(lines)


def format_host_time_line(now: float | None = None) -> str:
    """One-line form for pillar user prompts."""
    t = time.time() if now is None else now
    return f"Local time: {format_local_time(t)}. Clock period: {day_period(t)}."
