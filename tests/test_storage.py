"""Tests for Storage-level queries and the event cache."""

from datetime import UTC, datetime

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
