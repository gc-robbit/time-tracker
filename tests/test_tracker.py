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
    event = tracker.start()
    assert tracker.state() == "running"
    assert tracker.active_since() == event.ts == clock.current


def test_start_twice_raises(tracker: Tracker) -> None:
    tracker.start()
    with pytest.raises(InvalidTransitionError, match="already running"):
        tracker.start()


def test_start_while_paused_raises(tracker: Tracker) -> None:
    tracker.start()
    tracker.pause()
    with pytest.raises(InvalidTransitionError, match="paused"):
        tracker.start()


def test_pause_when_idle_raises(tracker: Tracker) -> None:
    with pytest.raises(InvalidTransitionError, match="Nothing to pause"):
        tracker.pause()


def test_pause_twice_raises(tracker: Tracker) -> None:
    tracker.start()
    tracker.pause()
    with pytest.raises(InvalidTransitionError, match="already paused"):
        tracker.pause()


def test_resume_when_idle_raises(tracker: Tracker) -> None:
    with pytest.raises(InvalidTransitionError, match="No session in progress"):
        tracker.resume()


def test_resume_when_running_raises(tracker: Tracker) -> None:
    tracker.start()
    with pytest.raises(InvalidTransitionError, match="already running"):
        tracker.resume()


def test_stop_when_idle_raises(tracker: Tracker) -> None:
    with pytest.raises(InvalidTransitionError, match="nothing to stop"):
        tracker.stop()


def test_pause_resume_stop_flow(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start()
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
    tracker.start()
    clock.advance(hours=4)
    tracker.pause()
    session = tracker.stop()
    assert session.worked == timedelta(hours=4)


def test_persisted_state_survives_reopen(tmp_path, clock: FakeClock) -> None:
    path = tmp_path / "persist.db"
    with Storage(path) as storage:
        Tracker(storage, now=clock).start()
    with Storage(path) as storage:
        assert Tracker(storage, now=clock).state() == "running"


# -- intervals and summaries ----------------------------------------------


def test_current_session_includes_live_interval(
    tracker: Tracker, clock: FakeClock
) -> None:
    tracker.start()
    clock.advance(hours=1, minutes=15)
    session = tracker.current_session()
    assert session is not None
    assert session.worked == timedelta(hours=1, minutes=15)
    assert session.ended is None


def test_today_delta_and_flex_balance(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start()
    clock.advance(hours=9)
    summary = tracker.today_summary()
    assert summary.worked == timedelta(hours=9)
    assert summary.target == DEFAULT_WORKDAY
    assert summary.delta == timedelta(hours=1)
    assert tracker.flex_balance() == timedelta(hours=1)


def test_delta_counts_down_while_running(tracker: Tracker, clock: FakeClock) -> None:
    tracker.start()
    clock.advance(hours=4)
    assert tracker.today_summary().delta == -timedelta(hours=4)
    clock.advance(hours=2)
    assert tracker.today_summary().delta == -timedelta(hours=2)


def test_flex_balance_spans_days(tracker: Tracker, clock: FakeClock) -> None:
    # Day 1: work 9h -> +1h flex
    tracker.start()
    clock.advance(hours=9)
    tracker.stop()

    # Day 2: work 7h -> -1h, net balance 0
    clock.current = clock.current + timedelta(days=1)
    tracker.start()
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
    tracker.start()
    clock.advance(hours=4)
    summary = tracker.today_summary()
    assert summary.target == timedelta(hours=6)
    assert summary.delta == -timedelta(hours=2)
    assert tracker.target() == timedelta(hours=6)


def test_default_target_when_unset(tracker: Tracker) -> None:
    assert tracker.target() == timedelta(hours=8)


def test_interval_crossing_midnight_belongs_to_start_day(
    tracker: Tracker, clock: FakeClock
) -> None:
    local_tz = datetime.now().astimezone().tzinfo
    start_local = datetime(2026, 10, 20, 23, 0, tzinfo=local_tz)
    clock.current = start_local.astimezone(UTC)
    tracker.start()
    clock.advance(hours=2)  # crosses local midnight into 2026-10-21
    tracker.stop()

    summaries = tracker.day_summaries()
    assert [summary.day for summary in summaries] == [start_local.date()]
    assert summaries[0].worked == timedelta(hours=2)
