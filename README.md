# time-tracker

A CLI time tracker that records start/pause/resume/stop sessions in SQLite and
measures each day against a configurable workday length — showing your running
delta (flex time) for today and your cumulative flex balance.

## Usage

```sh
uv run time-tracker start     # begin tracking
uv run time-tracker pause     # pause the running session
uv run time-tracker continue  # resume a paused session (alias: resume)
uv run time-tracker stop      # end the current session and show its totals
uv run time-tracker status    # current state + today's delta (default command)
uv run time-tracker report    # per-day worked/target/delta/balance table
uv run time-tracker config    # show the workday target (default: 8h)
uv run time-tracker config workday 6h30m  # change it (8, 8h, 6h30m, 8:30, 45m)
```

`status` shows a live view, e.g.:

```
Status : running — started 09:12:34, elapsed 4:10:22
Today  : 4:10 worked / 8:00 target
Delta  : -3:50 vs today's target
Flex   : +1:30 overall
```

- **Delta** — worked time today vs today's target, updating live while running.
- **Flex** — cumulative balance across all tracked days (`worked − target` per day).

## Storage

Sessions are stored as an append-only event log (`start`, `pause`, `resume`,
`stop`) in a SQLite database:

- macOS: `~/Library/Application Support/time-tracker/time-tracker.db`
- Linux: `$XDG_DATA_HOME/time-tracker/time-tracker.db` (or `~/.local/share/...`)
- Override with the `TIME_TRACKER_DB` environment variable.

Timestamps are stored in UTC; days are grouped by local date, and an interval
that crosses midnight counts toward the day it started.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```sh
uv sync              # install dependencies (including dev group)
uv run pytest        # run tests
uv run ruff check .  # lint
uv run ruff format . # format
```
