"""Domain logic: tracking state machine, intervals, and flex-time summaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .storage import Event, ManualEntry, Storage

DEFAULT_WORKDAY = timedelta(hours=8)
ZERO = timedelta(0)

AWAY_KINDS = ("vacation", "sick")

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"


class InvalidTransitionError(Exception):
    """A command that is not valid in the current tracking state."""


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    project: str = ""

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class Session:
    started: datetime
    intervals: tuple[Interval, ...]
    project: str = ""
    ended: datetime | None = None

    @property
    def worked(self) -> timedelta:
        return sum((interval.duration for interval in self.intervals), ZERO)

    @property
    def wall_time(self) -> timedelta | None:
        if self.ended is None:
            return None
        return self.ended - self.started


@dataclass(frozen=True)
class DaySummary:
    day: date
    worked: timedelta
    target: timedelta
    away: timedelta = ZERO

    @property
    def delta(self) -> timedelta:
        # A day with away time is neutral: the leave covers the target,
        # regardless of how much was actually worked that day.
        if self.away:
            return ZERO
        return self.worked - self.target


@dataclass(frozen=True)
class ProjectDay:
    project: str
    day: date
    worked: timedelta


class Tracker:
    def __init__(
        self,
        storage: Storage,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.storage = storage
        self.now = now or (lambda: datetime.now(UTC))

    @property
    def last_event(self) -> Event | None:
        return self.storage.last_event()

    def state(self) -> str:
        last = self.last_event
        if last is None or last.event_type == "stop":
            return STATE_IDLE
        if last.event_type == "pause":
            return STATE_PAUSED
        return STATE_RUNNING

    def active_since(self) -> datetime | None:
        """Timestamp of the last transition into the current active state."""
        if self.state() == STATE_IDLE:
            return None
        last = self.last_event
        return last.ts if last else None

    # -- state transitions -------------------------------------------------

    def start(self, project: str, at: datetime | None = None) -> Event:
        state = self.state()
        if state == STATE_RUNNING:
            raise InvalidTransitionError(
                "Time tracking is already running ('stop' to end it)."
            )
        if state == STATE_PAUSED:
            raise InvalidTransitionError(
                "A session is already in progress but paused "
                "('continue' to resume it or 'stop' to end it)."
            )
        project = project.strip()
        if not project:
            raise ValueError("project name must not be empty")
        now = self.now()
        moment = at if at is not None else now
        if moment.tzinfo is None:
            raise ValueError("start time must be timezone-aware")
        if moment > now:
            raise ValueError("start time must not be in the future")
        last = self.last_event
        if last is not None and moment < last.ts:
            raise ValueError(
                "start time must not be earlier than the last recorded event"
            )
        return self.storage.add_event("start", moment, project=project)

    def pause(self) -> Event:
        state = self.state()
        if state == STATE_IDLE:
            raise InvalidTransitionError(
                "Nothing to pause — no session is in progress ('start' to begin)."
            )
        if state == STATE_PAUSED:
            raise InvalidTransitionError("Time tracking is already paused.")
        return self.storage.add_event("pause", self.now())

    def resume(self) -> Event:
        state = self.state()
        if state == STATE_IDLE:
            raise InvalidTransitionError("No session in progress ('start' to begin).")
        if state == STATE_RUNNING:
            raise InvalidTransitionError("Time tracking is already running.")
        return self.storage.add_event("resume", self.now())

    def stop(self) -> Session:
        if self.state() == STATE_IDLE:
            raise InvalidTransitionError("No session in progress — nothing to stop.")
        self.storage.add_event("stop", self.now())
        session = self.current_session()
        if session is None:  # pragma: no cover - defensive
            raise InvalidTransitionError("No session in progress — nothing to stop.")
        return session

    def log_day(
        self,
        day: date,
        worked: timedelta,
        project: str | None = None,
        *,
        replace: bool = False,
    ) -> ManualEntry:
        """Record worked time for a local day after the fact.

        Entries add to any tracked time for the day. With ``replace`` the
        manual total becomes the whole day's total, overriding tracked time
        and discarding earlier manual entries for that day.
        """
        minutes = int(worked.total_seconds() // 60)
        if minutes <= 0:
            raise ValueError("worked time must be at least one minute")
        name = (project or "").strip() or None
        return self._add_manual_entry(day, minutes, name, None, replace)

    def log_away_day(
        self, day: date, kind: str, *, replace: bool = False
    ) -> ManualEntry:
        """Record a full working day of away time (vacation or sick leave).

        The configured workday target is used as the duration, and away time
        cannot be attributed to a project.
        """
        normalized = (kind or "").strip().lower() or None
        if normalized not in AWAY_KINDS:
            expected = ", ".join(AWAY_KINDS)
            raise ValueError(f"unknown away kind {kind!r} (expected {expected})")
        minutes = int(self.target().total_seconds() // 60)
        return self._add_manual_entry(day, minutes, None, normalized, replace)

    def _add_manual_entry(
        self,
        day: date,
        minutes: int,
        project: str | None,
        kind: str | None,
        replace: bool,
    ) -> ManualEntry:
        if day > self.now().astimezone().date():
            raise ValueError("day must not be in the future")
        for entry in self.storage.manual_entries():
            if entry.day == day and entry.replaces and not replace:
                raise ValueError(
                    f"{day.isoformat()} already has an overriding entry "
                    "(use 'log ... --replace' to change it)"
                )
        return self.storage.add_manual_entry(
            day, minutes, project=project, replaces=replace, kind=kind
        )

    # -- derived data ------------------------------------------------------

    def current_session(self) -> Session | None:
        """The session opened by the most recent 'start'.

        Includes the live interval when tracking is running. Returns None if
        no session has ever been started.
        """
        started: datetime | None = None
        intervals: list[Interval] = []
        open_since: datetime | None = None
        ended: datetime | None = None
        project = ""

        for event in self.storage.events():
            if event.event_type == "start":
                started = event.ts
                intervals = []
                open_since = event.ts
                ended = None
                project = event.project or ""
            elif started is None:
                continue
            elif event.event_type == "pause":
                if open_since is not None:
                    intervals.append(Interval(open_since, event.ts, project))
                    open_since = None
            elif event.event_type == "resume":
                if open_since is None:
                    open_since = event.ts
            elif event.event_type == "stop":
                if open_since is not None:
                    intervals.append(Interval(open_since, event.ts, project))
                    open_since = None
                ended = event.ts

        if started is None:
            return None
        if ended is None and open_since is not None:
            intervals.append(Interval(open_since, self.now(), project))
        return Session(started, tuple(intervals), project, ended)

    def intervals(self, end: datetime | None = None) -> list[Interval]:
        """All tracked intervals; the open one (if any) ends at `end`/now.

        Intervals that cross midnight belong to the day their start falls on.
        """
        moment = end or self.now()
        result: list[Interval] = []
        open_since: datetime | None = None
        project = ""
        for event in self.storage.events():
            if event.event_type == "start":
                if open_since is not None:
                    result.append(Interval(open_since, event.ts, project))
                open_since = event.ts
                project = event.project or ""
            elif event.event_type == "resume":
                if open_since is None:
                    open_since = event.ts
            elif open_since is not None:
                result.append(Interval(open_since, event.ts, project))
                open_since = None
        if open_since is not None:
            result.append(Interval(open_since, moment, project))
        return result

    @property
    def default_project(self) -> str | None:
        """The configured default project, if any."""
        raw = self.storage.get_setting("default_project")
        if raw is None:
            return None
        raw = raw.strip()
        return raw or None

    def remember_default_project(self, project: str | None) -> bool:
        """Adopt ``project`` as the default when none is configured yet."""
        name = (project or "").strip()
        if not name or self.default_project is not None:
            return False
        self.storage.set_setting("default_project", name)
        return True

    def target(self) -> timedelta:
        """The configured workday length (default 8 hours)."""
        raw = self.storage.get_setting("workday_minutes")
        if raw is None:
            return DEFAULT_WORKDAY
        try:
            minutes = int(raw)
        except ValueError:
            return DEFAULT_WORKDAY
        return timedelta(minutes=minutes) if minutes > 0 else DEFAULT_WORKDAY

    def flex_buffer(self) -> timedelta:
        """The configured initial flex balance (default zero)."""
        raw = self.storage.get_setting("flex_buffer_minutes")
        if raw is None:
            return ZERO
        try:
            minutes = int(raw)
        except ValueError:
            return ZERO
        return timedelta(minutes=minutes)

    def day_summaries(self, end: datetime | None = None) -> list[DaySummary]:
        target = self.target()
        worked_by_day, away_by_day = self._time_by_day(end)
        days = sorted(worked_by_day.keys() | away_by_day.keys())
        return [
            DaySummary(
                day,
                worked_by_day.get(day, ZERO),
                target,
                away_by_day.get(day, ZERO),
            )
            for day in days
        ]

    def _time_by_day(
        self, end: datetime | None = None
    ) -> tuple[dict[date, timedelta], dict[date, timedelta]]:
        """Worked and away time per local day."""
        worked_by_day: dict[date, timedelta] = {}
        away_by_day: dict[date, timedelta] = {}
        for interval in self.intervals(end):
            day = interval.start.astimezone().date()
            worked_by_day[day] = worked_by_day.get(day, ZERO) + interval.duration

        entries = self.storage.manual_entries()
        overrides = {entry.day: entry for entry in entries if entry.replaces}
        for entry in overrides.values():
            if entry.kind is None:
                worked_by_day[entry.day] = timedelta(minutes=entry.minutes)
            else:
                worked_by_day[entry.day] = ZERO
                away_by_day[entry.day] = timedelta(minutes=entry.minutes)
        for entry in entries:
            if entry.replaces or entry.day in overrides:
                continue
            totals = away_by_day if entry.kind is not None else worked_by_day
            totals[entry.day] = totals.get(entry.day, ZERO) + timedelta(
                minutes=entry.minutes
            )
        return worked_by_day, away_by_day

    def today_summary(self, end: datetime | None = None) -> DaySummary:
        moment = end or self.now()
        today = moment.astimezone().date()
        worked_by_day, away_by_day = self._time_by_day(end)
        return DaySummary(
            today,
            worked_by_day.get(today, ZERO),
            self.target(),
            away_by_day.get(today, ZERO),
        )

    def project_days(self, end: datetime | None = None) -> dict[str, list[ProjectDay]]:
        """Worked time per project, grouped by local day and sorted by date.

        Intervals from sessions started before projects existed group under "".
        Manual days without a project only affect the global flex balance.
        """
        totals: dict[str, dict[date, timedelta]] = {}
        entries = self.storage.manual_entries()
        overrides = {entry.day: entry for entry in entries if entry.replaces}
        for interval in self.intervals(end):
            day = interval.start.astimezone().date()
            if day in overrides:
                continue
            totals.setdefault(interval.project, {})
            totals[interval.project][day] = (
                totals[interval.project].get(day, ZERO) + interval.duration
            )
        for entry in entries:
            if (
                entry.replaces
                or entry.day in overrides
                or not entry.project
                or entry.kind is not None
            ):
                continue
            totals.setdefault(entry.project, {})
            totals[entry.project][entry.day] = totals[entry.project].get(
                entry.day, ZERO
            ) + timedelta(minutes=entry.minutes)
        for entry in overrides.values():
            if not entry.project or entry.kind is not None:
                continue
            totals.setdefault(entry.project, {})
            totals[entry.project][entry.day] = timedelta(minutes=entry.minutes)
        return {
            project: [
                ProjectDay(project, day, worked) for day, worked in sorted(days.items())
            ]
            for project, days in sorted(totals.items())
        }

    def flex_balance(self, end: datetime | None = None) -> timedelta:
        """Cumulative flex balance: the initial buffer plus daily deltas."""
        return self.flex_buffer() + sum(
            (summary.delta for summary in self.day_summaries(end)), ZERO
        )
