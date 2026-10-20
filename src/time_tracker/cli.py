"""Command-line interface for time-tracker."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

from .durations import (
    format_clock,
    format_duration,
    format_hours,
    format_signed,
    parse_duration,
)
from .storage import Storage
from .tracker import InvalidTransitionError, Tracker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="time-tracker",
        description="Track working time against a configurable workday length.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start", help="start tracking time")
    subparsers.add_parser("pause", help="pause the running session")
    subparsers.add_parser(
        "continue",
        aliases=["resume"],
        help="resume a paused session",
    )
    subparsers.add_parser("stop", help="stop the current session")
    subparsers.add_parser("status", help="show current status (default)")
    subparsers.add_parser("report", help="show per-day totals and flex balance")
    config = subparsers.add_parser("config", help="show or set configuration")
    config.add_argument(
        "name",
        nargs="?",
        choices=["workday"],
        help="setting to change",
    )
    config.add_argument("value", nargs="?", help="new value, e.g. 8h or 6h30m")
    return parser


def _clock(ts: datetime) -> str:
    return ts.astimezone().strftime("%H:%M:%S")


def _print_status(tracker: Tracker) -> None:
    state = tracker.state()
    active_since = tracker.active_since()
    if state == "running" and active_since is not None:
        elapsed = tracker.now() - active_since
        print(
            f"Status : running — started {_clock(active_since)}, "
            f"elapsed {format_clock(elapsed)}"
        )
    elif state == "paused" and active_since is not None:
        print(f"Status : paused since {_clock(active_since)}")
    else:
        last = tracker.last_event
        suffix = (
            f" — last event: {last.event_type} at {_clock(last.ts)}" if last else ""
        )
        print(f"Status : idle{suffix}")

    summary = tracker.today_summary()
    print(
        f"Today  : {format_duration(summary.worked)} worked / "
        f"{format_duration(summary.target)} target"
    )
    print(f"Delta  : {format_signed(summary.delta)} vs today's target")
    print(f"Flex   : {format_signed(tracker.flex_balance())} overall")


def _print_report(tracker: Tracker) -> None:
    summaries = tracker.day_summaries()
    if not summaries:
        print("No time tracked yet. Start a session with 'time-tracker start'.")
        return

    rows: list[tuple[str, str, str, str, str]] = [
        ("Date", "Worked", "Target", "Delta", "Balance")
    ]
    balance = timedelta(0)
    for summary in summaries:
        balance += summary.delta
        rows.append(
            (
                summary.day.isoformat(),
                format_duration(summary.worked),
                format_duration(summary.target),
                format_signed(summary.delta),
                format_signed(balance),
            )
        )

    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for index, row in enumerate(rows):
        cells = [
            cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
            for i, cell in enumerate(row)
        ]
        print("  ".join(cells))
        if index == 0:
            print("  ".join("-" * width for width in widths))


def _run_config(args: argparse.Namespace, tracker: Tracker) -> None:
    if args.name is None:
        print(f"Workday target: {format_hours(tracker.target())}")
        return
    if args.value is None:
        raise ValueError(f"missing value for setting '{args.name}'")
    minutes = int(parse_duration(args.value).total_seconds() // 60)
    if minutes <= 0:
        raise ValueError("workday target must be longer than zero")
    tracker.storage.set_setting("workday_minutes", str(minutes))
    print(f"Workday target set to {format_hours(timedelta(minutes=minutes))}.")


def _dispatch(args: argparse.Namespace, tracker: Tracker) -> None:
    command = args.command or "status"
    if command == "start":
        event = tracker.start()
        print(
            f"Started at {_clock(event.ts)}. Run 'time-tracker stop' when you're done."
        )
    elif command == "pause":
        event = tracker.pause()
        session = tracker.current_session()
        worked = session.worked if session else timedelta(0)
        print(
            f"Paused at {_clock(event.ts)}. "
            f"Session worked so far: {format_duration(worked)}."
        )
    elif command in ("continue", "resume"):
        event = tracker.resume()
        print(f"Resumed at {_clock(event.ts)}.")
    elif command == "stop":
        session = tracker.stop()
        wall_time = session.wall_time or timedelta(0)
        print(
            f"Stopped at {_clock(session.ended)}. "
            f"Session worked {format_duration(session.worked)} "
            f"(wall clock {format_duration(wall_time)})."
        )
    elif command == "config":
        _run_config(args, tracker)
    elif command == "report":
        _print_report(tracker)
    else:
        _print_status(tracker)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if not argv:
        argv = ["status"]
    args = build_parser().parse_args(argv)
    try:
        with Storage() as storage:
            _dispatch(args, Tracker(storage))
    except (InvalidTransitionError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
