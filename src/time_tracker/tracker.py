"""Domain logic: tracking state machine, intervals, and flex-time summaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .storage import Event, Storage

DEFAULT_WORKDAY = timedelta(hours=8)
ZERO = timedelta(0)

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

    @property
    def delta(self) -> timedelta:
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

    def day_summaries(self, end: datetime | None = None) -> list[DaySummary]:
        target = self.target()
        worked_by_day: dict[date, timedelta] = {}
        for interval in self.intervals(end):
            day = interval.start.astimezone().date()
            worked_by_day[day] = worked_by_day.get(day, ZERO) + interval.duration
        return [
            DaySummary(day, worked, target)
            for day, worked in sorted(worked_by_day.items())
        ]

    def today_summary(self, end: datetime | None = None) -> DaySummary:
        moment = end or self.now()
        today = moment.astimezone().date()
        worked = sum(
            (
                interval.duration
                for interval in self.intervals(end)
                if interval.start.astimezone().date() == today
            ),
            ZERO,
        )
        return DaySummary(today, worked, self.target())

    def project_days(self, end: datetime | None = None) -> dict[str, list[ProjectDay]]:
        """Worked time per project, grouped by local day and sorted by date.

        Intervals from sessions started before projects existed group under "".
        """
        totals: dict[str, dict[date, timedelta]] = {}
        for interval in self.intervals(end):
            day = interval.start.astimezone().date()
            totals.setdefault(interval.project, {})
            totals[interval.project][day] = (
                totals[interval.project].get(day, ZERO) + interval.duration
            )
        return {
            project: [
                ProjectDay(project, day, worked) for day, worked in sorted(days.items())
            ]
            for project, days in sorted(totals.items())
        }

    def flex_balance(self, end: datetime | None = None) -> timedelta:
        """Cumulative flex balance: sum of daily (worked - target) deltas."""
        return sum((summary.delta for summary in self.day_summaries(end)), ZERO)
