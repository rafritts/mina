"""Host wall-clock injection — pure helpers."""
from __future__ import annotations

import time

from src.brain.time_context import (
    day_period,
    format_host_time_block,
    format_host_time_line,
    format_local_time,
)


def _ts(hour: int, minute: int = 0) -> float:
    """Local timestamp for today at hour:minute (keeps DST/local correct)."""
    lt = time.localtime()
    return time.mktime((
        lt.tm_year, lt.tm_mon, lt.tm_mday,
        hour, minute, 0,
        lt.tm_wday, lt.tm_yday, lt.tm_isdst,
    ))


def test_day_period_bands():
    assert day_period(_ts(9, 0)) == "MORNING"
    assert day_period(_ts(12, 0)) == "MORNING"
    assert day_period(_ts(12, 1)) == "DAYTIME"
    assert day_period(_ts(15, 30)) == "DAYTIME"
    assert day_period(_ts(20, 0)) == "DAYTIME"
    assert day_period(_ts(20, 1)) == "EVENING"
    assert day_period(_ts(23, 30)) == "EVENING"
    assert day_period(_ts(23, 31)) == "NIGHTTIME"
    assert day_period(_ts(2, 0)) == "NIGHTTIME"
    assert day_period(_ts(8, 0)) == "NIGHTTIME"
    assert day_period(_ts(8, 1)) == "MORNING"


def test_format_local_time_shape():
    s = format_local_time(_ts(15, 45))
    assert "202" in s  # year
    assert ":" in s
    assert ("AM" in s) or ("PM" in s)


def test_host_time_block_mouth():
    block = format_host_time_block(now=_ts(22, 15), for_mouth=True)
    assert block.startswith("[Turn context]")
    assert "Local time:" in block
    assert "Clock period: EVENING" in block
    assert "circadian" in block.lower()
    assert "fiction" in block.lower()


def test_host_time_block_idle():
    now = _ts(14, 0)
    block = format_host_time_block(
        last_activity_ts=now - 7200,
        now=now,
        for_mouth=False,
    )
    assert "Last activity: 2.0 hours ago" in block
    assert "Clock period: DAYTIME" in block


def test_host_time_line():
    line = format_host_time_line(_ts(3, 0))
    assert line.startswith("Local time:")
    assert "NIGHTTIME" in line
