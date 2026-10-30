"""Tests for Storage-level queries and the event cache."""

import sqlite3
from datetime import UTC, date, datetime

from time_tracker.storage import Storage

TS = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)


def test_last_event_is_none_when_empty(tmp_path) -> None:
    with Storage(tmp_path / "storage.db") as storage:
        assert storage.last_event() is None


def test_last_event_returns_most_recent(tmp_path) -> None:
    with Storage(tmp_path / "storage.db") as storage:
        first = storage.add_event("start", TS, project="web")
        second = storage.add_event("stop", TS)

        last = storage.last_event()
        assert last is not None
        assert last.id == second.id == first.id + 1
        assert last.event_type == "stop"
        assert last.ts == TS


def test_events_cache_sees_new_events(tmp_path) -> None:
    with Storage(tmp_path / "storage.db") as storage:
        storage.add_event("start", TS, project="web")
        assert [event.event_type for event in storage.events()] == ["start"]

        storage.add_event("stop", TS)
        assert [event.event_type for event in storage.events()] == ["start", "stop"]


def test_events_returns_defensive_copies(tmp_path) -> None:
    with Storage(tmp_path / "storage.db") as storage:
        storage.add_event("start", TS, project="web")
        events = storage.events()
        events.clear()
        assert [event.event_type for event in storage.events()] == ["start"]


def test_manual_entries_cache_sees_new_entries(tmp_path) -> None:
    day = date(2026, 10, 20)
    with Storage(tmp_path / "storage.db") as storage:
        storage.add_manual_entry(day, 480, project="web")
        assert [entry.minutes for entry in storage.manual_entries()] == [480]

        storage.add_manual_entry(day, 30, project="web")
        assert [entry.minutes for entry in storage.manual_entries()] == [480, 30]


def test_manual_replacement_discards_entries_for_the_day(tmp_path) -> None:
    day = date(2026, 10, 20)
    next_day = date(2026, 10, 21)
    with Storage(tmp_path / "storage.db") as storage:
        storage.add_manual_entry(day, 120, project="web")
        storage.add_manual_entry(day, 60, project="web")
        storage.add_manual_entry(next_day, 240, project="web")

        replacement = storage.add_manual_entry(
            day, 360, project="design", replaces=True
        )

        entries = storage.manual_entries()
        assert replacement.replaces
        assert [(entry.day, entry.minutes) for entry in entries] == [
            (day, 360),
            (next_day, 240),
        ]


def test_manual_entries_return_defensive_copies(tmp_path) -> None:
    with Storage(tmp_path / "storage.db") as storage:
        storage.add_manual_entry(date(2026, 10, 20), 480, project="web")
        entries = storage.manual_entries()
        entries.clear()
        assert [entry.minutes for entry in storage.manual_entries()] == [480]


def test_refresh_sees_writes_from_another_connection(tmp_path) -> None:
    path = tmp_path / "shared.db"
    with Storage(path) as reader, Storage(path) as writer:
        assert reader.events() == []
        assert reader.manual_entries() == []

        writer.add_event("start", TS, project="web")
        writer.add_manual_entry(date(2026, 10, 20), 30, project="web")

        # Cached reads stay stale until the view explicitly refreshes.
        assert reader.events() == []
        assert reader.manual_entries() == []

        reader.refresh()

        assert [event.event_type for event in reader.events()] == ["start"]
        assert [entry.minutes for entry in reader.manual_entries()] == [30]


def test_manual_entry_records_away_kind(tmp_path) -> None:
    day = date(2026, 10, 20)
    with Storage(tmp_path / "storage.db") as storage:
        entry = storage.add_manual_entry(day, 480, kind="vacation")

        assert entry.kind == "vacation"
        assert entry.project is None
        assert storage.manual_entries()[0].kind == "vacation"


def test_legacy_manual_entries_table_gains_kind_column(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE manual_entries ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "day TEXT NOT NULL, "
        "minutes INTEGER NOT NULL, "
        "project TEXT, "
        "replaces INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO manual_entries (day, minutes) VALUES ('2026-10-20', 480)")
    conn.commit()
    conn.close()

    with Storage(path) as storage:
        assert [entry.kind for entry in storage.manual_entries()] == [None]
        entry = storage.add_manual_entry(date(2026, 10, 21), 60, kind="sick")
        assert entry.kind == "sick"
