from datetime import time, timedelta

import pytest

from time_tracker.durations import (
    format_clock,
    format_duration,
    format_hours,
    format_signed,
    parse_duration,
    parse_time_of_day,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8", timedelta(hours=8)),
        ("8h", timedelta(hours=8)),
        ("6h30m", timedelta(hours=6, minutes=30)),
        ("6h30", timedelta(hours=6, minutes=30)),
        ("45m", timedelta(minutes=45)),
        ("8:30", timedelta(hours=8, minutes=30)),
        ("0:05", timedelta(minutes=5)),
        (" 8H ", timedelta(hours=8)),
    ],
)
def test_parse_duration(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "8:", "8:99", "90m", "-1h"])
def test_parse_duration_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("9:30", time(9, 30)),
        ("09:30", time(9, 30)),
        ("09:30:15", time(9, 30, 15)),
        ("0:00", time(0, 0)),
        ("23:59", time(23, 59)),
        (" 9:05 ", time(9, 5)),
    ],
)
def test_parse_time_of_day(text: str, expected: time) -> None:
    assert parse_time_of_day(text) == expected


@pytest.mark.parametrize(
    "text", ["", "abc", "9", "9:5", "24:00", "9:60", "9:30:60", "-1:00"]
)
def test_parse_time_of_day_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_time_of_day(text)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(hours=4, minutes=10), "4:10"),
        (timedelta(hours=-3, minutes=-50), "-3:50"),
        (timedelta(0), "0:00"),
        (timedelta(minutes=-1), "-0:01"),
        (timedelta(days=1), "24:00"),
    ],
)
def test_format_duration(delta: timedelta, expected: str) -> None:
    assert format_duration(delta) == expected


def test_format_signed() -> None:
    assert format_signed(timedelta(minutes=30)) == "+0:30"
    assert format_signed(timedelta(minutes=-30)) == "-0:30"
    assert format_signed(timedelta(0)) == "+0:00"


def test_format_clock() -> None:
    assert format_clock(timedelta(hours=1, minutes=2, seconds=3)) == "1:02:03"
    assert format_clock(timedelta(seconds=59)) == "0:00:59"


def test_format_hours() -> None:
    assert format_hours(timedelta(hours=8)) == "8h"
    assert format_hours(timedelta(hours=6, minutes=30)) == "6h30m"
