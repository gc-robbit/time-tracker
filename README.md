# time-tracker

A CLI time tracker that records start/pause/resume/stop sessions in SQLite
against named projects, and measures each day globally against a configurable
workday length — showing your running delta (flex time) for today and your
cumulative flex balance.

## Usage

The examples below assume `time-tracker` is available on your `PATH`. Grab the
single-file distribution from the [releases
page](https://github.com/gc-robbit/time-tracker/releases) (`chmod +x
time-tracker` after downloading) and put it anywhere on your `PATH` — it is a
self-contained [uv script](https://docs.astral.sh/uv/guides/scripts/) that needs
no clone or install. See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for how it
is built.

```sh
time-tracker start web        # begin tracking on a project
time-tracker start            # falls back to the default project
time-tracker start web --at 09:00   # begin at a specific local time today
time-tracker pause            # pause the running session (aliases: lunch, out)
time-tracker continue         # resume a paused session (aliases: resume, back)
time-tracker stop             # end the current session and show its totals
time-tracker status           # current state + today's delta (default command)
time-tracker report           # worked time per project + global flex history
time-tracker report web       # worked time for one project only
time-tracker config           # show all settings
time-tracker config workday 6h30m         # set the workday target
time-tracker config default_project web   # set the default project
```

A project is **required** to start: pass one on the command line or configure
a default with `config default_project <name>` — starting with neither fails
with an error. Project names are created implicitly on first use (quote names
containing spaces). Durations accept `8`, `8h`, `6h30m`, `8:30` or `45m`.

By default `start` uses the current time. Use `--at HH:MM` (or
`--at HH:MM:SS`) to backdate the start to a local time today; the time must
not be in the future or earlier than the last recorded event.

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

## Development

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for development setup and how
the single-file distribution is built.
