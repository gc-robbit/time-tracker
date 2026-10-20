# time-tracker

A CLI time tracker that records start/pause/resume/stop sessions in SQLite
against named projects, and measures each day globally against a configurable
workday length — showing your running delta (flex time) for today and your
cumulative flex balance.

## Usage

```sh
uv run time-tracker start web        # begin tracking on a project
uv run time-tracker start            # falls back to the default project
uv run time-tracker pause            # pause the running session
uv run time-tracker continue         # resume a paused session (alias: resume)
uv run time-tracker stop             # end the current session and show its totals
uv run time-tracker status           # current state + today's delta (default command)
uv run time-tracker report           # worked time per project + global flex history
uv run time-tracker report web       # worked time for one project only
uv run time-tracker config           # show all settings
uv run time-tracker config workday 6h30m         # set the workday target
uv run time-tracker config default_project web   # set the default project
```

A project is **required** to start: pass one on the command line or configure
a default with `config default_project <name>` — starting with neither fails
with an error. Project names are created implicitly on first use (quote names
containing spaces). Durations accept `8`, `8h`, `6h30m`, `8:30` or `45m`.

`status` shows a live view, e.g.:

```
Status : running, project 'web' — started 09:12:34, elapsed 4:10:22
Today  : 4:10 worked / 8:00 target
Delta  : -3:50 vs today's target
Flex   : +1:30 overall
```

- **Delta** — worked time today vs today's target, updating live while running.
- **Flex** — cumulative balance across all tracked days (`worked − target` per
  day). Flex is **global**: it does not depend on projects.
- **Report** — worked time broken down per project and day; the trailing
  `Flex (global)` section keeps the daily delta/balance history.

## Storage

Sessions are stored as an append-only event log (`start`, `pause`, `resume`,
`stop`) in a SQLite database; the project is recorded on each `start` event:

- macOS: `~/Library/Application Support/time-tracker/time-tracker.db`
- Linux: `$XDG_DATA_HOME/time-tracker/time-tracker.db` (or `~/.local/share/...`)
- Override with the `TIME_TRACKER_DB` environment variable.

Timestamps are stored in UTC; days are grouped by local date, and an interval
that crosses midnight counts toward the day it started. Databases created
before projects existed are migrated automatically.

## Single-file distribution

`dist/time-tracker` is a generated, standalone copy of this project as a
single [PEP 723](https://peps.python.org/pep-0723/) script with inline `uv`
metadata. It only uses the Python standard library, so anyone with
[uv](https://docs.astral.sh/uv/) can run it from anywhere — no clone, no
install:

```sh
./dist/time-tracker start web       # shebang runs uv for you
uv run --script dist/time-tracker status
```

The file has no `.py` extension on purpose: it can be copied or renamed
freely (e.g. onto your `PATH` as `time-tracker`) and keeps working, because
the `--script` flag lives in its shebang. Note that plain
`uv run dist/time-tracker` won't be recognized as a script — pass `--script`.

It is **generated** from `src/time_tracker/` — the package remains the source
of truth. After changing the package, regenerate it:

```sh
uv run tools/build_dist.py          # rewrite dist/time-tracker
uv run tools/build_dist.py --check  # verify it is up to date
```

A test fails if the distribution drifts from the sources, so it can't get
stale.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```sh
uv sync              # install dependencies (including dev group)
uv run pytest        # run tests
uv run ruff check .  # lint
uv run ruff format . # format
```
