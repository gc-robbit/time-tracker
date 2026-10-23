import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from time_tracker.storage import Storage
from time_tracker.tracker import (
    DEFAULT_WORKDAY,
    InvalidTransitionError,
    Tracker,
)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    # 2026-10-20 07:00 UTC; tests only assert against locally-converted dates
    return FakeClock(datetime(2026, 10, 20, 7, 0, tzinfo=UTC))


@pytest.fixture
def tracker(tmp_path, clock) -> Tracker:
    storage = Storage(tmp_path / "test.db")
    yield Tracker(storage, now=clock)
    storage.close()


# -- state machine ---------------------------------------------------------


def test_initial_state_is_idle(tracker: Tracker) -> None:
    assert tracker.state() == "idle"
    assert tracker.active_since() is None
    assert tracker.last_event is None


def test_start_moves_to_running(tracker: Tracker, clock: FakeClock) -> None:
    event = tracker.start("web")
    assert tracker.state() == "running"
    assert tracker.active_since() == event.ts == clock.current


def test_start_twice_raises(tracker: Tracker) -> None:
    tracker.start("web")
    with pytest.raises(InvalidTransitionError, match="already running"):
        tracker.start("web")


def test_start_at_backdates_the_session(tracker: Tracker, clock: FakeClock) -> None:
    started = clock.current - timedelta(hours=2)
    event = tracker.start("web", at=started)

    assert event.ts == started
    assert tracker.active_since() == started
    session = tracker.current_session()
    assert session is not None
    assert session.worked == timedelta(hours=2)


def test_start_at_rejects_a_future_time(tracker: Tracker, clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="future"):
        tracker.start("web", at=clock.current + timedelta(minutes=1))


def test_start_at_rejects_a_naive_time(tracker: Tracker, clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        tracker.start("web", at=clock.current.replace(tzinfo=None))


def test_start_at_rejects_overlapping_previous_session(
    tracker: Tracker, clock: FakeClock
) -> None:
    tracker.start("web")
    clock.advance(hours=2)
    tracker.stop()
    with pytest.raises(ValueError, match="earlier than the last recorded event"):
        tracker.start("web", at=clock.current - timedelta(hours=1))


def test_start_at_after_previous_stop_is_allowed(
    tracker: Tracker, clock: FakeClock
) -> None:
    tracker.start("web")
    clock.advance(hours=1)
    tracker.stop()
    clock.advance(hours=2)
    tracker.start("web", at=clock.current - timedelta(hours=1))

    session = tracker.current_session()
    assert session is not None
    assert session.worked == timedelta(hours=1)
    assert tracker.today_summary().worked == timedelta(hours=2)


def test_start_while_paused_raises(tracker: Tracker) -> None:
    tracker.start("web")
    tracker.pause()
    with pytest.raises(InvalidTransitionError, match="paused"):
        tracker.start("web")


def test_pause_when_idle_raises(tracker: Tracker) -> None:
    with pytest.raises(InvalidTransitionError, match="Nothing to pause"):
        tracker.pause()


def test_pause_twice_raises(tracker: Tracker) -> None:
    tracker.start("web")
    tracker.pause()
    with pytest.raises(InvalidTransitionError, match="already paused"):
        tracker.pause()


def test_resume_when_idle_raises(tracker: Tracker) -> None:
    with pytest.raises(InvalidTransitionError, match="No session in progress"):
        tracker.resume()


def test_resume_when_running_raises(tracker: Tracker) -> None:
    tracker.start("web")
    with pytest.raises(InvalidTransitionError, match="already running"):
        tracker.resume()


def test_stop_when_idle_raises(tracker: Tracker) -> None:
    with pytest.raises(InvalidTransitionError, match="nothing to stop"):
        tracker.stop()


def test_pause_resume_stop_flow(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start("web")
    clock.advance(hours=2)
    tracker.pause()
    assert tracker.state() == "paused"

    clock.advance(hours=1)  # unpaid gap while paused
    tracker.resume()
    assert tracker.state() == "running"

    clock.advance(minutes=30)
    session = tracker.stop()

    assert tracker.state() == "idle"
    assert session.worked == timedelta(hours=2, minutes=30)
    assert session.wall_time == timedelta(hours=3, minutes=30)
    assert session.ended is not None


def test_stop_while_paused_works(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start("web")
    clock.advance(hours=4)
    tracker.pause()
    session = tracker.stop()
    assert session.worked == timedelta(hours=4)


def test_persisted_state_survives_reopen(tmp_path, clock: FakeClock) -> None:
    path = tmp_path / "persist.db"
    with Storage(path) as storage:
        Tracker(storage, now=clock).start("web")
    with Storage(path) as storage:
        assert Tracker(storage, now=clock).state() == "running"


# -- intervals and summaries ----------------------------------------------


def test_current_session_includes_live_interval(
    tracker: Tracker, clock: FakeClock
) -> None:
    tracker.start("web")
    clock.advance(hours=1, minutes=15)
    session = tracker.current_session()
    assert session is not None
    assert session.worked == timedelta(hours=1, minutes=15)
    assert session.ended is None


def test_today_delta_and_flex_balance(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start("web")
    clock.advance(hours=9)
    summary = tracker.today_summary()
    assert summary.worked == timedelta(hours=9)
    assert summary.target == DEFAULT_WORKDAY
    assert summary.delta == timedelta(hours=1)
    assert tracker.flex_balance() == timedelta(hours=1)


def test_delta_counts_down_while_running(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start("web")
    clock.advance(hours=4)
    assert tracker.today_summary().delta == -timedelta(hours=4)
    clock.advance(hours=2)
    assert tracker.today_summary().delta == -timedelta(hours=2)


def test_flex_balance_spans_days(tracker: Tracker, clock: FakeClock) -> None:
    # Day 1: work 9h -> +1h flex
    tracker.start("web")
    clock.advance(hours=9)
    tracker.stop()

    # Day 2: different project, work 7h -> -1h, net balance 0
    clock.current = clock.current + timedelta(days=1)
    tracker.start("design")
    clock.advance(hours=7)
    tracker.stop()

    summaries = tracker.day_summaries()
    assert [summary.delta for summary in summaries] == [
        timedelta(hours=1),
        -timedelta(hours=1),
    ]
    assert tracker.flex_balance() == timedelta(0)


def test_configured_workday_target(tracker: Tracker, clock: FakeClock) -> None:
    tracker.storage.set_setting("workday_minutes", "360")  # 6h workday
    tracker.start("web")
    clock.advance(hours=4)
    summary = tracker.today_summary()
    assert summary.target == timedelta(hours=6)
    assert summary.delta == -timedelta(hours=2)
    assert tracker.target() == timedelta(hours=6)


def test_default_target_when_unset(tracker: Tracker) -> None:
    assert tracker.target() == timedelta(hours=8)


def test_flex_buffer_defaults_to_zero(tracker: Tracker) -> None:
    assert tracker.flex_buffer() == timedelta(0)


def test_flex_buffer_is_added_to_the_balance(
    tracker: Tracker, clock: FakeClock
) -> None:
    tracker.storage.set_setting("flex_buffer_minutes", "90")  # +1h30 initial flex
    tracker.start("web")
    clock.advance(hours=9)  # +1h today

    assert tracker.flex_buffer() == timedelta(hours=1, minutes=30)
    assert tracker.flex_balance() == timedelta(hours=2, minutes=30)


def test_negative_flex_buffer_is_supported(tracker: Tracker) -> None:
    tracker.storage.set_setting("flex_buffer_minutes", "-120")
    assert tracker.flex_buffer() == timedelta(hours=-2)
    assert tracker.flex_balance() == timedelta(hours=-2)


def test_invalid_flex_buffer_is_ignored(tracker: Tracker) -> None:
    tracker.storage.set_setting("flex_buffer_minutes", "banana")
    assert tracker.flex_buffer() == timedelta(0)


def test_interval_crossing_midnight_belongs_to_start_day(
    tracker: Tracker, clock: FakeClock
) -> None:
    local_tz = datetime.now().astimezone().tzinfo
    start_local = datetime(2026, 10, 20, 23, 0, tzinfo=local_tz)
    clock.current = start_local.astimezone(UTC)
    tracker.start("web")
    clock.advance(hours=2)  # crosses local midnight into 2026-10-21
    tracker.stop()

    summaries = tracker.day_summaries()
    assert [summary.day for summary in summaries] == [start_local.date()]
    assert summaries[0].worked == timedelta(hours=2)


# -- projects --------------------------------------------------------------


def test_start_requires_project(tracker: Tracker) -> None:
    with pytest.raises(ValueError, match="project"):
        tracker.start("   ")


def test_session_and_intervals_carry_project(
    tracker: Tracker, clock: FakeClock
) -> None:
    tracker.start("web")
    clock.advance(hours=2)
    tracker.pause()
    clock.advance(minutes=10)
    tracker.resume()
    clock.advance(minutes=30)
    session = tracker.stop()

    assert session.project == "web"
    assert session.intervals
    assert all(interval.project == "web" for interval in session.intervals)
    assert all(interval.project == "web" for interval in tracker.intervals())


def test_default_project_roundtrip(tracker: Tracker) -> None:
    assert tracker.default_project is None
    tracker.storage.set_setting("default_project", "web")
    assert tracker.default_project == "web"
    tracker.storage.set_setting("default_project", "   ")
    assert tracker.default_project is None


def test_flex_is_global_across_projects(tracker: Tracker, clock: FakeClock) -> None:
    # Two projects, 4h each on the same day: the 8h target is met exactly.
    tracker.start("web")
    clock.advance(hours=4)
    tracker.stop()
    tracker.start("design")
    clock.advance(hours=4)
    tracker.stop()

    summary = tracker.today_summary()
    assert summary.worked == timedelta(hours=8)
    assert summary.delta == timedelta(0)
    assert tracker.flex_balance() == timedelta(0)

    project_days = tracker.project_days()
    assert set(project_days) == {"web", "design"}
    assert project_days["web"][0].worked == timedelta(hours=4)
    assert project_days["design"][0].worked == timedelta(hours=4)


def test_project_days_spans_days(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start("web")
    clock.advance(hours=9)
    tracker.stop()
    clock.current = clock.current + timedelta(days=1)
    tracker.start("design")
    clock.advance(hours=7)
    tracker.stop()

    project_days = tracker.project_days()
    assert list(project_days) == ["design", "web"]
    assert sum((day.worked for day in project_days["web"]), timedelta(0)) == (
        timedelta(hours=9)
    )
    assert sum((day.worked for day in project_days["design"]), timedelta(0)) == (
        timedelta(hours=7)
    )
    # Flex stays global: +1h and -1h net out regardless of project.
    assert tracker.flex_balance() == timedelta(0)


def test_legacy_db_without_project_column_is_migrated(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "event_type TEXT NOT NULL, "
        "ts TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO events (event_type, ts) VALUES "
        "('start', '2026-10-20T07:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO events (event_type, ts) VALUES "
        "('stop', '2026-10-20T09:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    with Storage(path) as storage:
        events = storage.events()
        assert [event.project for event in events] == [None, None]
        tracker = Tracker(storage)
        intervals = tracker.intervals()
        assert len(intervals) == 1
        assert intervals[0].project == ""
        assert set(tracker.project_days()) == {""}
