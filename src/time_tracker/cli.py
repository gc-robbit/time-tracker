"""Command-line interface for time-tracker."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

from .durations import (
    format_clock,
    format_duration,
    format_hours,
    format_signed,
    parse_duration,
    parse_signed_duration,
    parse_time_of_day,
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
    start.add_argument(
        "--at",
        metavar="HH:MM",
        help="start at this local time today instead of now (e.g. 09:30)",
    )
    log = subparsers.add_parser(
        "log", help="record worked time for a past day after the fact"
    )
    log.add_argument(
        "date",
        metavar="DATE",
        help="local date (YYYY-MM-DD, 'today' or 'yesterday')",
    )
    log.add_argument(
        "duration",
        metavar="DURATION",
        help="worked time, e.g. 7h30m (accepts the usual duration formats)",
    )
    log.add_argument(
        "project",
        nargs="?",
        help="project to attribute the time to (falls back to the configured default)",
    )
    log.add_argument(
        "--replace",
        action="store_true",
        help="replace all tracked and manual time for that day",
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
        "report",
        help="show the global flex history (optionally broken down per project)",
    )
    report.add_argument("project", nargs="?", help="only report on this project")
    report.add_argument(
        "--all",
        action="store_true",
        help="report on all projects (by default only the global report is shown)",
    )
    report.add_argument(
        "--start",
        metavar="DATE",
        help="start date (YYYY-MM-DD, 'today' or 'yesterday')",
    )
    report.add_argument(
        "--end",
        metavar="DATE",
        help="end date (YYYY-MM-DD, 'today' or 'yesterday')",
    )
    config = subparsers.add_parser("config", help="show or set configuration")
    # Let signed durations such as '-2h' through as a positional value instead
    # of argparse treating them as unknown options.
    config._negative_number_matcher = re.compile(r"^-\d")
    config.add_argument(
        "name",
        nargs="?",
        choices=["workday", "default_project", "flex_buffer"],
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


def _in_range(day: date, start: date | None, end: date | None) -> bool:
    return (start is None or day >= start) and (end is None or day <= end)


def _print_flex_section(
    tracker: Tracker, start: date | None = None, end: date | None = None
) -> None:
    print("Flex (global):")
    summaries = tracker.day_summaries()
    balance = tracker.flex_buffer()
    if start is not None:
        # Carry the balance from before the requested range into it.
        balance += sum(
            (summary.delta for summary in summaries if summary.day < start),
            timedelta(0),
        )
    if balance:
        print(f"Starting balance: {format_signed(balance)}")
    rows = []
    for summary in summaries:
        if not _in_range(summary.day, start, end):
            continue
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


def _print_report(
    tracker: Tracker,
    project: str | None = None,
    *,
    all_projects: bool = False,
    start: date | None = None,
    end: date | None = None,
) -> None:
    project_days = {
        name: [day for day in days if _in_range(day.day, start, end)]
        for name, days in tracker.project_days().items()
    }
    project_days = {name: days for name, days in project_days.items() if days}

    if project is not None:
        days = project_days.get(project, [])
        if not days:
            suffix = " in that date range" if start or end else ""
            print(f"No time tracked for project '{project}'{suffix}.")
            return
        print(f"Project: {_project_label(project)}")
        _print_project_days(days)
        return

    summaries = tracker.day_summaries()
    if not summaries:
        print(
            "No time tracked yet. Start a session with 'time-tracker start <project>'."
        )
        return

    if all_projects:
        for index, (name, days) in enumerate(project_days.items()):
            if index:
                print()
            print(f"Project: {_project_label(name)}")
            _print_project_days(days)
        if project_days:
            print()
    _print_flex_section(tracker, start=start, end=end)


def _run_config(args: argparse.Namespace, tracker: Tracker) -> None:
    if args.name is None:
        print(f"Workday target: {format_hours(tracker.target())}")
        print(f"Initial flex buffer: {format_signed(tracker.flex_buffer())}")
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
    if args.name == "flex_buffer":
        minutes = int(parse_signed_duration(args.value).total_seconds() // 60)
        tracker.storage.set_setting("flex_buffer_minutes", str(minutes))
        print(
            f"Initial flex buffer set to {format_signed(timedelta(minutes=minutes))}."
        )
        return
    project = args.value.strip()
    if not project:
        raise ValueError("project name must not be empty")
    tracker.storage.set_setting("default_project", project)
    print(f"Default project set to '{project}'.")


def _resolve_start_time(tracker: Tracker, value: str | None) -> datetime | None:
    """Turn a local time of day into an aware datetime for today."""
    if value is None:
        return None
    parsed = parse_time_of_day(value)
    local_now = tracker.now().astimezone()
    return datetime.combine(local_now.date(), parsed).astimezone()


def _resolve_day(tracker: Tracker, value: str) -> date:
    """Parse a past local date from ISO format or a relative alias."""
    text = value.strip().lower()
    today = tracker.now().astimezone().date()
    if text == "today":
        day = today
    elif text == "yesterday":
        day = today - timedelta(days=1)
    else:
        try:
            day = date.fromisoformat(text)
        except ValueError:
            raise ValueError(
                f"invalid date {value!r} (expected YYYY-MM-DD, 'today' or 'yesterday')"
            ) from None
    if day > today:
        raise ValueError("date must not be in the future")
    return day


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
        event = tracker.start(project, _resolve_start_time(tracker, args.at))
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
    elif command == "log":
        day = _resolve_day(tracker, args.date)
        worked = parse_duration(args.duration)
        project = (args.project or "").strip() or tracker.default_project
        tracker.log_day(day, worked, project, replace=args.replace)
        summary = next(
            (summary for summary in tracker.day_summaries() if summary.day == day),
            None,
        )
        total = format_duration(summary.worked) if summary else "0:00"
        target = f" for '{project}'" if project else ""
        if args.replace:
            print(
                f"Replaced all time on {day.isoformat()} with "
                f"{format_duration(worked)}{target} (day total {total})."
            )
        else:
            print(
                f"Logged {format_duration(worked)}{target} on "
                f"{day.isoformat()} (day total {total})."
            )
    elif command == "report":
        project = (args.project or "").strip() or None
        if project is not None and args.all:
            raise ValueError("cannot combine a project with --all")
        start = _resolve_day(tracker, args.start) if args.start else None
        end = _resolve_day(tracker, args.end) if args.end else None
        if start is not None and end is not None and start > end:
            raise ValueError("start date must not be after end date")
        _print_report(
            tracker,
            project,
            all_projects=args.all,
            start=start,
            end=end,
        )
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
