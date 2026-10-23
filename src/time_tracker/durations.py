"""Parsing and formatting helpers for durations."""

from __future__ import annotations

import re
from datetime import time, timedelta

_DURATION_RE = re.compile(
    r"^(?:(?P<hours>\d+(?:\.\d+)?)h)?(?:(?P<minutes>\d+)m?)?$",
)

_TIME_RE = re.compile(
    r"^(?P<hours>\d{1,2}):(?P<minutes>\d{2})(?::(?P<seconds>\d{2}))?$",
)


def parse_duration(text: str) -> timedelta:
    """Parse a duration such as '8', '8h', '6h30m', '45m' or '8:30'."""
    text = text.strip().lower()
    if not text:
        raise ValueError("duration must not be empty (expected e.g. 8h, 6h30m or 8:30)")

    if ":" in text:
        hours_text, separator, minutes_text = text.partition(":")
        if (
            not separator
            or not hours_text.isdigit()
            or not minutes_text.isdigit()
            or int(minutes_text) > 59
        ):
            raise ValueError(
                f"invalid duration {text!r} (expected e.g. 8h, 6h30m, 8:30 or 45m)"
            )
        return timedelta(hours=int(hours_text), minutes=int(minutes_text))

    if text.isdigit():
        return timedelta(hours=int(text))

    match = _DURATION_RE.match(text)
    if not match or not any(match.groupdict().values()):
        raise ValueError(
            f"invalid duration {text!r} (expected e.g. 8h, 6h30m, 8:30 or 45m)"
        )
    minutes = int(match["minutes"] or 0)
    if minutes > 59:
        raise ValueError(f"invalid duration {text!r} (minutes must be 0-59)")
    return timedelta(hours=float(match["hours"] or 0), minutes=minutes)


def parse_signed_duration(text: str) -> timedelta:
    """Parse a duration with an optional leading sign ('1h30m', '+45m', '-2h')."""
    text = text.strip()
    sign = 1
    if text[:1] in ("+", "-"):
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    return sign * parse_duration(text)


def parse_time_of_day(text: str) -> time:
    """Parse a local time such as '9:30', '09:30' or '09:30:15'."""
    text = text.strip()
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"invalid time {text!r} (expected e.g. 9:30 or 09:30:15)")
    hours = int(match["hours"])
    minutes = int(match["minutes"])
    seconds = int(match["seconds"] or 0)
    if hours > 23 or minutes > 59 or seconds > 59:
        raise ValueError(f"invalid time {text!r} (expected e.g. 9:30 or 09:30:15)")
    return time(hours, minutes, seconds)


def format_duration(delta: timedelta) -> str:
    """Format a duration as H:MM, rounded down to whole minutes ('4:10', '-3:50')."""
    total_minutes = int(delta.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else ""
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours}:{minutes:02d}"


def format_signed(delta: timedelta) -> str:
    """Format a duration with an explicit sign ('+0:30', '-3:50')."""
    if delta < timedelta(0):
        return format_duration(delta)
    return f"+{format_duration(delta)}"


def format_clock(delta: timedelta) -> str:
    """Format a duration as H:MM:SS, rounded down to whole seconds."""
    total_seconds = int(delta.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, rest = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{sign}{hours}:{minutes:02d}:{seconds:02d}"


def format_hours(delta: timedelta) -> str:
    """Format a duration compactly ('8h', '6h30m')."""
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h{minutes:02d}m"
