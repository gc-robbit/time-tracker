"""SQLite storage for tracking events and settings."""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

EVENT_TYPES = ("start", "pause", "resume", "stop")


def default_db_path() -> Path:
    """Resolve the database path.

    Honours the TIME_TRACKER_DB environment variable; otherwise uses the
    platform's per-user data directory.
    """
    override = os.environ.get("TIME_TRACKER_DB")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "time-tracker" / "time-tracker.db"


@dataclass(frozen=True)
class Event:
    id: int
    event_type: str
    ts: datetime
    project: str | None = None


@dataclass(frozen=True)
class ManualEntry:
    id: int
    day: date
    minutes: int
    project: str | None = None
    replaces: bool = False
    kind: str | None = None


class Storage:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._events_cache: list[Event] | None = None
        self._manual_cache: list[ManualEntry] | None = None
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL CHECK (event_type IN
                        ('start', 'pause', 'resume', 'stop')),
                    ts TEXT NOT NULL,
                    project TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS manual_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day TEXT NOT NULL,
                    minutes INTEGER NOT NULL CHECK (minutes > 0),
                    project TEXT,
                    replaces INTEGER NOT NULL DEFAULT 0
                        CHECK (replaces IN (0, 1)),
                    kind TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS manual_entries_one_override
                    ON manual_entries (day) WHERE replaces = 1;
                """
            )
            columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(events)")
            }
            if "project" not in columns:
                self._conn.execute("ALTER TABLE events ADD COLUMN project TEXT")
            columns = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(manual_entries)")
            }
            if "kind" not in columns:
                self._conn.execute("ALTER TABLE manual_entries ADD COLUMN kind TEXT")

    def add_event(
        self, event_type: str, ts: datetime, project: str | None = None
    ) -> Event:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type!r}")
        if ts.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        utc_ts = ts.astimezone(UTC)
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO events (event_type, ts, project) VALUES (?, ?, ?)",
                (event_type, utc_ts.isoformat(), project),
            )
        self._events_cache = None
        return Event(
            id=cursor.lastrowid, event_type=event_type, ts=utc_ts, project=project
        )

    def events(self) -> list[Event]:
        """All events in order, read once per Storage instance.

        The parsed log is cached in memory; add_event() invalidates it.
        Returns a copy so callers cannot mutate the cache.
        """
        if self._events_cache is None:
            rows = self._conn.execute(
                "SELECT id, event_type, ts, project FROM events ORDER BY id"
            ).fetchall()
            self._events_cache = [
                Event(
                    id=row["id"],
                    event_type=row["event_type"],
                    ts=datetime.fromisoformat(row["ts"]),
                    project=row["project"],
                )
                for row in rows
            ]
        return list(self._events_cache)

    def add_manual_entry(
        self,
        day: date,
        minutes: int,
        project: str | None = None,
        *,
        replaces: bool = False,
        kind: str | None = None,
    ) -> ManualEntry:
        """Record minutes for a local day.

        Additive entries stack on top of tracked time; an entry with
        ``replaces`` makes that day's total authoritative and discards any
        earlier manual entries for the day. A non-null ``kind`` marks away
        time (such as vacation or sick leave) rather than worked time.
        """
        if minutes <= 0:
            raise ValueError("manual time must be longer than zero")
        with self._conn:
            if replaces:
                self._conn.execute(
                    "DELETE FROM manual_entries WHERE day = ?", (day.isoformat(),)
                )
            cursor = self._conn.execute(
                "INSERT INTO manual_entries (day, minutes, project, replaces, kind) "
                "VALUES (?, ?, ?, ?, ?)",
                (day.isoformat(), minutes, project, int(replaces), kind),
            )
        self._manual_cache = None
        return ManualEntry(
            id=cursor.lastrowid,
            day=day,
            minutes=minutes,
            project=project,
            replaces=replaces,
            kind=kind,
        )

    def manual_entries(self) -> list[ManualEntry]:
        """All manual day entries, sorted by day and insertion order."""
        if self._manual_cache is None:
            rows = self._conn.execute(
                "SELECT id, day, minutes, project, replaces, kind "
                "FROM manual_entries ORDER BY day, id"
            ).fetchall()
            self._manual_cache = [
                ManualEntry(
                    id=row["id"],
                    day=date.fromisoformat(row["day"]),
                    minutes=row["minutes"],
                    project=row["project"],
                    replaces=bool(row["replaces"]),
                    kind=row["kind"],
                )
                for row in rows
            ]
        return list(self._manual_cache)

    def refresh(self) -> None:
        """Discard cached rows so writes from other processes become visible."""
        self._events_cache = None
        self._manual_cache = None

    def last_event(self) -> Event | None:
        """The most recent event, or None when no events exist."""
        row = self._conn.execute(
            "SELECT id, event_type, ts, project FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return Event(
            id=row["id"],
            event_type=row["event_type"],
            ts=datetime.fromisoformat(row["ts"]),
            project=row["project"],
        )

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
