"""Live terminal status view with keyboard controls."""

from __future__ import annotations

import os
import select
import sqlite3
import sys
import termios
import tty

from .durations import (
    format_clock,
    format_duration,
    format_signed,
    format_wall_clock,
)
from .tracker import (
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RUNNING,
    InvalidTransitionError,
    Tracker,
)

REFRESH_SECONDS = 1.0
QUIT_KEYS = frozenset({"q", "\x03", "\x04"})


def status_lines(tracker: Tracker) -> list[str]:
    """The shared four-line status summary used by ``status`` and ``watch``."""
    state = tracker.state()
    active_since = tracker.active_since()
    session = tracker.current_session()
    project = f", project '{session.project}'" if session and session.project else ""
    if state == STATE_RUNNING and active_since is not None:
        elapsed = tracker.now() - active_since
        lines = [
            f"Status : running{project} — started "
            f"{format_wall_clock(active_since)}, elapsed {format_clock(elapsed)}"
        ]
    elif state == STATE_PAUSED and active_since is not None:
        lines = [f"Status : paused{project} since {format_wall_clock(active_since)}"]
    else:
        last = tracker.last_event
        suffix = (
            f" — last event: {last.event_type} at {format_wall_clock(last.ts)}"
            if last
            else ""
        )
        lines = [f"Status : idle{suffix}"]

    summary = tracker.today_summary()
    away = f" + {format_duration(summary.away)} away" if summary.away else ""
    lines.append(
        f"Today  : {format_duration(summary.worked)} worked{away} / "
        f"{format_duration(summary.target)} target"
    )
    lines.append(f"Delta  : {format_signed(summary.delta)} vs today's target")
    lines.append(f"Flex   : {format_signed(tracker.flex_balance())} overall")
    return lines


def key_hints(tracker: Tracker, project: str | None = None) -> str:
    """A one-line reminder of the keys that make sense in the current state."""
    state = tracker.state()
    if state == STATE_RUNNING:
        return "[space] pause  [x] stop  [q] quit"
    if state == STATE_PAUSED:
        return "[space] continue  [x] stop  [q] quit"
    name = (project or "").strip() or tracker.default_project
    label = f" '{name}'" if name else ""
    return f"[space] start{label}  [q] quit"


def render_frame(
    tracker: Tracker,
    message: str | None = None,
    *,
    project: str | None = None,
    width: int | None = None,
) -> str:
    """Build one complete live-view frame, optionally clipped to ``width``."""
    lines = status_lines(tracker)
    if message:
        lines.extend(("", message))
    lines.extend(("", key_hints(tracker, project)))
    if width is not None and width > 0:
        lines = [line[:width] for line in lines]
    return "\n".join(lines) + "\n"


def apply_key(
    tracker: Tracker, key: str, project: str | None = None
) -> tuple[bool, str | None]:
    """Apply one key press, returning ``(keep_running, message)``."""
    try:
        if key in QUIT_KEYS:
            if tracker.state() == STATE_IDLE:
                return False, None
            return False, _stop(tracker)
        state = tracker.state()
        if key == " ":
            if state == STATE_IDLE:
                return True, _start(tracker, project)
            if state == STATE_RUNNING:
                tracker.pause()
                return True, "Paused."
            tracker.resume()
            return True, "Resumed."
        if key == "s":
            if state != STATE_IDLE:
                return True, "Already tracking; use space to pause or x to stop."
            return True, _start(tracker, project)
        if key == "p":
            tracker.pause()
            return True, "Paused."
        if key == "c":
            tracker.resume()
            return True, "Resumed."
        if key == "x":
            return True, _stop(tracker)
        return True, None
    except (InvalidTransitionError, ValueError, sqlite3.Error) as error:
        return key not in QUIT_KEYS, f"Error: {error}"


def _stop(tracker: Tracker) -> str:
    session = tracker.stop()
    ended = session.ended or tracker.now()
    name = f" '{session.project}'" if session.project else ""
    return (
        f"Stopped at {format_wall_clock(ended)}. "
        f"Session{name} worked {format_duration(session.worked)}."
    )


def _start(tracker: Tracker, project: str | None) -> str:
    name = (project or "").strip() or tracker.default_project
    if not name:
        return (
            "No project configured — set one with "
            "'time-tracker config default_project <name>' or run "
            "'time-tracker watch <project>'."
        )
    event = tracker.start(name)
    message = f"Started '{name}' at {format_wall_clock(event.ts)}."
    if tracker.remember_default_project(name):
        message += f" Set '{name}' as the default project."
    return message


def run_view(
    tracker: Tracker,
    project: str | None = None,
    *,
    interval: float = REFRESH_SECONDS,
) -> None:
    """Run the interactive view until the user quits."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError(
            "watch requires an interactive terminal; use 'time-tracker status' "
            "for a one-off view"
        )

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    message: str | None = None
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l\x1b[2J\x1b[H")
        sys.stdout.flush()
        while True:
            tracker.storage.refresh()
            _draw(tracker, message, project)
            key = _read_key(fd, interval)
            if key is None:
                continue
            keep_running, message = apply_key(tracker, key, project)
            if not keep_running:
                tracker.storage.refresh()
                _draw(tracker, message, project)
                break
    except KeyboardInterrupt:
        _, message = apply_key(tracker, "\x03", project)
        try:
            tracker.storage.refresh()
            _draw(tracker, message, project)
        except (KeyboardInterrupt, OSError, sqlite3.Error):
            pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()


def _draw(tracker: Tracker, message: str | None, project: str | None) -> None:
    frame = render_frame(
        tracker,
        message,
        project=project,
        width=_terminal_width(),
    )
    sys.stdout.write(_paint_frame(frame))
    sys.stdout.flush()


def _paint_frame(frame: str) -> str:
    """Overwrite the previous frame, clearing short lines and removed rows."""
    lines = frame.splitlines()
    body = "\n".join(f"{line}\x1b[K" for line in lines)
    return "\x1b[H" + body + "\n\x1b[J"


def _read_key(fd: int, timeout: float) -> str | None:
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None
    data = os.read(fd, 1)
    if not data:
        return "\x04"
    return data.decode(errors="ignore")


def _terminal_width() -> int | None:
    try:
        columns = os.get_terminal_size(sys.stdout.fileno()).columns
    except OSError:
        return None
    return columns if columns > 0 else None
