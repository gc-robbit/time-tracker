"""Command-line interface for time-tracker."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta

from .durations import (
    format_clock,
    format_duration,
    format_hours,
    format_signed,
    parse_duration,
)
from .storage import Storage, default_db_path
from .tracker import InvalidTransitionError, ProjectDay, Tracker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="time-tracker",
        description="Track working time against a configurable workday length.",
    )
    subparsers = parser.add_subparsers(dest="command")
    start = subparsers.add_parser("start", help="start tracking time")
    start.add_argument(
        "project",
        nargs="?",
        help="project to track time against (falls back to the configured default)",
    )
    subparsers.add_parser(
        "pause",
        aliases=["lunch", "out"],
        help="pause the running session",
    )
    subparsers.add_parser(
        "continue",
        aliases=["resume", "back"],
        help="resume a paused session",
    )
    subparsers.add_parser("stop", help="stop the current session")
    subparsers.add_parser("status", help="show current status (default)")
    report = subparsers.add_parser(
        "report", help="show worked time per project and the global flex history"
    )
    report.add_argument("project", nargs="?", help="only report on this project")
    config = subparsers.add_parser("config", help="show or set configuration")
    config.add_argument(
        "name",
        nargs="?",
        choices=["workday", "default_project"],
        help="setting to change",
    )
    config.add_argument("value", nargs="?", help="new value, e.g. 8h or 6h30m")
    return parser


def _clock(ts: datetime) -> str:
    return ts.astimezone().strftime("%H:%M:%S")


def _print_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    all_rows = [headers, *rows]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    for index, row in enumerate(all_rows):
        cells = [
            cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
            for i, cell in enumerate(row)
        ]
        print("  ".join(cells))
        if index == 0:
            print("  ".join("-" * width for width in widths))


def _project_label(project: str) -> str:
    return project or "(unnamed)"


def _print_status(tracker: Tracker) -> None:
    state = tracker.state()
    active_since = tracker.active_since()
    session = tracker.current_session()
    project = f", project '{session.project}'" if session and session.project else ""
    if state == "running" and active_since is not None:
        elapsed = tracker.now() - active_since
        print(
            f"Status : running{project} — started {_clock(active_since)}, "
            f"elapsed {format_clock(elapsed)}"
        )
    elif state == "paused" and active_since is not None:
        print(f"Status : paused{project} since {_clock(active_since)}")
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


def _print_project_days(days: list[ProjectDay]) -> None:
    rows = [(day.day.isoformat(), format_duration(day.worked)) for day in days]
    _print_table(("Date", "Worked"), rows)
    total = sum((day.worked for day in days), timedelta(0))
    print(f"Total: {format_duration(total)}")


def _print_flex_section(tracker: Tracker) -> None:
    print("Flex (global):")
    rows = []
    balance = timedelta(0)
    for summary in tracker.day_summaries():
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
    _print_table(("Date", "Worked", "Target", "Delta", "Balance"), rows)


def _print_report(tracker: Tracker, project: str | None = None) -> None:
    project_days = tracker.project_days()
    if project is not None:
        days = project_days.get(project, [])
        if not days:
            print(f"No time tracked for project '{project}'.")
            return
        print(f"Project: {_project_label(project)}")
        _print_project_days(days)
        return

    if not project_days:
        print(
            "No time tracked yet. Start a session with 'time-tracker start <project>'."
        )
        return
    for index, (name, days) in enumerate(project_days.items()):
        if index:
            print()
        print(f"Project: {_project_label(name)}")
        _print_project_days(days)
    print()
    _print_flex_section(tracker)


def _run_config(args: argparse.Namespace, tracker: Tracker) -> None:
    if args.name is None:
        print(f"Workday target: {format_hours(tracker.target())}")
        default = tracker.default_project
        print(f"Default project: {default if default else '(not set)'}")
        return
    if args.value is None:
        raise ValueError(f"missing value for setting '{args.name}'")
    if args.name == "workday":
        minutes = int(parse_duration(args.value).total_seconds() // 60)
        if minutes <= 0:
            raise ValueError("workday target must be longer than zero")
        tracker.storage.set_setting("workday_minutes", str(minutes))
        print(f"Workday target set to {format_hours(timedelta(minutes=minutes))}.")
        return
    project = args.value.strip()
    if not project:
        raise ValueError("project name must not be empty")
    tracker.storage.set_setting("default_project", project)
    print(f"Default project set to '{project}'.")


def _dispatch(args: argparse.Namespace, tracker: Tracker) -> None:
    command = args.command or "status"
    if command == "start":
        project = (args.project or "").strip() or tracker.default_project
        if not project:
            raise ValueError(
                "no project given and no default project configured "
                "(use 'time-tracker start <project>' or set one with "
                "'time-tracker config default_project <name>')"
            )
        event = tracker.start(project)
        print(
            f"Started '{project}' at {_clock(event.ts)}. "
            "Run 'time-tracker stop' when you're done."
        )
    elif command in ("pause", "lunch", "out"):
        event = tracker.pause()
        session = tracker.current_session()
        worked = session.worked if session else timedelta(0)
        where = f" (project '{session.project}')" if session and session.project else ""
        print(
            f"Paused at {_clock(event.ts)}{where}. "
            f"Session worked so far: {format_duration(worked)}."
        )
    elif command in ("continue", "resume", "back"):
        event = tracker.resume()
        print(f"Resumed at {_clock(event.ts)}.")
    elif command == "stop":
        session = tracker.stop()
        wall_time = session.wall_time or timedelta(0)
        name = f" '{session.project}'" if session.project else ""
        print(
            f"Stopped at {_clock(session.ended)}. "
            f"Session{name} worked {format_duration(session.worked)} "
            f"(wall clock {format_duration(wall_time)})."
        )
    elif command == "config":
        _run_config(args, tracker)
    elif command == "report":
        _print_report(tracker, args.project.strip() if args.project else None)
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
    except sqlite3.Error as error:
        print(
            f"Database error: {error} (db: {default_db_path()})",
            file=sys.stderr,
        )
        return 1
    return 0
