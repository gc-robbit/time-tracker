from datetime import UTC, datetime, timedelta

import pytest

from time_tracker.storage import Storage
from time_tracker.tracker import STATE_IDLE, STATE_PAUSED, STATE_RUNNING, Tracker
from time_tracker.view import (
    _paint_frame,
    apply_key,
    key_hints,
    render_frame,
    status_lines,
)


class FixedClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 20, 7, 0, tzinfo=UTC))


@pytest.fixture
def tracker(tmp_path, clock: FixedClock) -> Tracker:
    storage = Storage(tmp_path / "view.db")
    yield Tracker(storage, now=clock)
    storage.close()


def test_status_lines_match_the_status_command(tracker: Tracker) -> None:
    assert status_lines(tracker) == [
        "Status : idle",
        "Today  : 0:00 worked / 8:00 target",
        "Delta  : -8:00 vs today's target",
        "Flex   : +0:00 overall",
    ]


def test_status_lines_running_and_elapsed(tracker: Tracker, clock: FixedClock) -> None:
    tracker.start("web")
    clock.advance(hours=1, minutes=2, seconds=3)

    lines = status_lines(tracker)

    assert lines[0].startswith("Status : running, project 'web' — started ")
    assert lines[0].endswith("elapsed 1:02:03")
    assert lines[1] == "Today  : 1:02 worked / 8:00 target"


def test_status_lines_show_away_time(tracker: Tracker) -> None:
    tracker.log_away_day(tracker.now().astimezone().date(), "vacation")

    lines = status_lines(tracker)

    assert "Today  : 0:00 worked + 8:00 away / 8:00 target" in lines
    assert "Delta  : +0:00 vs today's target" in lines


def test_render_frame_shows_state_specific_hints(tracker: Tracker) -> None:
    assert "[space] start  [q] quit" in render_frame(tracker)

    tracker.start("web")
    assert "[space] pause  [x] stop  [q] quit" in render_frame(tracker)

    tracker.pause()
    assert "[space] continue  [x] stop  [q] quit" in render_frame(tracker)


def test_render_frame_uses_the_project_argument_in_the_idle_hint(
    tracker: Tracker,
) -> None:
    assert "[space] start 'web'  [q] quit" in render_frame(tracker, project="web")


def test_render_frame_includes_messages_and_clips_to_width(tracker: Tracker) -> None:
    frame = render_frame(tracker, "Something went wrong", width=12)

    assert "Something we" in frame
    assert all(len(line) <= 12 for line in frame.splitlines())


def test_render_frame_ignores_non_positive_width(tracker: Tracker) -> None:
    assert render_frame(tracker, width=0) == render_frame(tracker)


def test_paint_frame_clears_each_line_and_removed_rows() -> None:
    output = _paint_frame("first\n\nthird\n")

    assert output == "\x1b[Hfirst\x1b[K\n\x1b[K\nthird\x1b[K\n\x1b[J"


def test_render_frame_elapsed_updates_as_time_passes(
    tracker: Tracker, clock: FixedClock
) -> None:
    tracker.start("web")
    first = render_frame(tracker)
    clock.advance(seconds=5)
    second = render_frame(tracker)

    assert first != second
    assert "elapsed 0:00:05" in second


def test_space_cycles_start_pause_resume_and_stop(tracker: Tracker) -> None:
    keep_running, message = apply_key(tracker, " ", project="web")

    assert keep_running
    assert message is not None and "Started 'web'" in message
    assert tracker.state() == STATE_RUNNING
    assert tracker.default_project == "web"

    keep_running, message = apply_key(tracker, " ")

    assert keep_running
    assert message == "Paused."
    assert tracker.state() == STATE_PAUSED

    keep_running, message = apply_key(tracker, " ")

    assert keep_running
    assert message == "Resumed."
    assert tracker.state() == STATE_RUNNING

    keep_running, message = apply_key(tracker, "x")

    assert keep_running
    assert message is not None and message.startswith("Stopped at ")
    assert tracker.state() == STATE_IDLE


def test_explicit_pause_continue_and_stop_keys(tracker: Tracker) -> None:
    tracker.start("web")

    assert apply_key(tracker, "p") == (True, "Paused.")
    assert tracker.state() == STATE_PAUSED

    assert apply_key(tracker, "c") == (True, "Resumed.")
    assert tracker.state() == STATE_RUNNING

    keep_running, message = apply_key(tracker, "x")
    assert keep_running
    assert message is not None and "Session 'web' worked" in message
    assert tracker.state() == STATE_IDLE


def test_invalid_transitions_return_messages_instead_of_raising(
    tracker: Tracker,
) -> None:
    keep_running, message = apply_key(tracker, "p")
    assert keep_running
    assert message is not None and message.startswith("Error:")
    assert tracker.state() == STATE_IDLE

    tracker.start("web")
    keep_running, message = apply_key(tracker, "c")
    assert keep_running
    assert message is not None and message.startswith("Error:")
    assert tracker.state() == STATE_RUNNING

    keep_running, message = apply_key(tracker, "s")
    assert keep_running
    assert message == "Already tracking; use space to pause or x to stop."


def test_start_key_requires_a_project(tracker: Tracker) -> None:
    keep_running, message = apply_key(tracker, " ")

    assert keep_running
    assert message is not None and "No project configured" in message
    assert tracker.state() == STATE_IDLE


def test_start_key_uses_the_configured_default(tracker: Tracker) -> None:
    tracker.storage.set_setting("default_project", "web")

    keep_running, message = apply_key(tracker, "s")

    assert keep_running
    assert message is not None and "Started 'web'" in message
    assert tracker.state() == STATE_RUNNING


def test_quit_keys_leave_an_idle_view_alone(tracker: Tracker) -> None:
    for key in ("q", "\x03", "\x04"):
        assert apply_key(tracker, key) == (False, None)
        assert tracker.state() == STATE_IDLE


@pytest.mark.parametrize("key", ["q", "\x03", "\x04"])
def test_quit_keys_stop_a_running_session(tracker: Tracker, key: str) -> None:
    tracker.start("web")

    keep_running, message = apply_key(tracker, key)

    assert not keep_running
    assert message is not None and message.startswith("Stopped at ")
    assert "Session 'web' worked" in message
    assert tracker.state() == STATE_IDLE


def test_quit_while_paused_stops_the_session(tracker: Tracker) -> None:
    tracker.start("web")
    tracker.pause()

    keep_running, message = apply_key(tracker, "q")

    assert not keep_running
    assert message is not None and message.startswith("Stopped at ")
    assert tracker.state() == STATE_IDLE


def test_unknown_keys_are_ignored(tracker: Tracker) -> None:
    assert apply_key(tracker, "?") == (True, None)
    assert key_hints(tracker) == "[space] start  [q] quit"
