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
time-tracker report           # global flex history
time-tracker report --all     # also break worked time down per project
time-tracker report web       # worked time for one project only
time-tracker report --start 2026-10-01 --end 2026-10-15  # limit the range
time-tracker log 2026-10-20 7h30m        # record a past day after the fact
time-tracker log yesterday 7h30m web     # ... attributed to a project
time-tracker log 2026-10-20 8h --replace # override everything for that day
time-tracker config           # show all settings
time-tracker config workday 6h30m         # set the workday target
time-tracker config flex_buffer 10h       # set an initial flex balance
time-tracker config default_project web   # set the default project
```

A project is **required** to start: pass one on the command line or configure
a default with `config default_project <name>` — starting with neither fails
with an error. The first project you name (with `start` or `log`) is also
remembered as the default when none is configured yet, so later commands can
omit it; naming a different project afterwards leaves the default unchanged.
Project names are created implicitly on first use (quote names containing
spaces). Durations accept `8`, `8h`, `6h30m`, `8:30` or `45m`.

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
- **Initial flex buffer** — an optional starting balance added to Flex, set with
  `config flex_buffer` (positive or negative, e.g. `10h` or `-2h30m`). It is
  useful for carrying flex in from before you started using the tracker.
- **Report** — shows the global daily delta/balance history, starting from the
  initial buffer. Pass `--all` to also break worked time down per project, or
  name a project to report on just that one. `--start DATE` and `--end DATE`
  limit any report to an inclusive date range (accepting `YYYY-MM-DD`, `today`
  or `yesterday`); the flex balance carried into the range is shown as the
  starting balance.

## Recording a past day

Use `log` to fill in a day you did not track live:

```sh
time-tracker log 2026-10-20 7h30m          # log time for that day
time-tracker log yesterday 7h30m web       # attribute it to a project
time-tracker log 2026-10-20 8h --replace   # make 8h the day's total
```

The date accepts `YYYY-MM-DD`, `today` or `yesterday`; future dates are
rejected. Durations use the same formats as elsewhere (`7h30m`, `7:30`, `45m`).

- Additions stack with any time tracked that day, so you can fill in the gaps
  around partially tracked sessions.
- `--replace` makes the given duration the authoritative total for that date.
  It overrides tracked sessions and discards earlier manual entries for the day.
  A day can only be replaced again with another `--replace`.
- The project argument is optional and falls back to `default_project`. Manual
  days with no project still count toward the global flex balance but do not
  appear in per-project reports.
- Manual days appear in `status`, `report` and the flex history exactly like
  tracked days, including the daily target and delta.

## Storage

Sessions are stored as an append-only event log (`start`, `pause`, `resume`,
`stop`) in a SQLite database; the project is recorded on each `start` event:

- macOS: `~/Library/Application Support/time-tracker/time-tracker.db`
- Linux: `$XDG_DATA_HOME/time-tracker/time-tracker.db` (or `~/.local/share/...`)
- Override with the `TIME_TRACKER_DB` environment variable.

Timestamps are stored in UTC; days are grouped by local date, and an interval
that crosses midnight counts toward the day it started. Backfilled days live
in a separate `manual_entries` table: additive entries merge with the event
log, while a replacement entry takes precedence over everything for that date.
Databases created before projects existed are migrated automatically.

## Development

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for development setup and how
the single-file distribution is built.
