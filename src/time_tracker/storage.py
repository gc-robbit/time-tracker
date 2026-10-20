"""SQLite storage for tracking events and settings."""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
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


class Storage:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
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
                """
            )
            columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(events)")
            }
            if "project" not in columns:
                self._conn.execute("ALTER TABLE events ADD COLUMN project TEXT")

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
        return Event(
            id=cursor.lastrowid, event_type=event_type, ts=utc_ts, project=project
        )

    def events(self) -> list[Event]:
        rows = self._conn.execute(
            "SELECT id, event_type, ts, project FROM events ORDER BY id"
        ).fetchall()
        return [
            Event(
                id=row["id"],
                event_type=row["event_type"],
                ts=datetime.fromisoformat(row["ts"]),
                project=row["project"],
            )
            for row in rows
        ]

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
