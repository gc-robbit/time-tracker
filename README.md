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
time-tracker watch            # live status view with keyboard controls
time-tracker watch web        # ... starting 'web' when idle
time-tracker report           # global flex history
time-tracker report --all     # also break worked time down per project
time-tracker report web       # worked time for one project only
time-tracker report --start 2026-10-01 --end 2026-10-15  # limit the range
time-tracker log 2026-10-20 7h30m        # record a past day after the fact
time-tracker log yesterday 7h30m web     # ... attributed to a project
time-tracker log 2026-10-20 8h --replace # override everything for that day
time-tracker log 2026-10-20 --vacay      # a full day of vacation
time-tracker log yesterday --sick        # a full day of sick leave
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
not be in the future or earlier than the last recorded event. Local times that
are skipped when the clocks go forward are rejected; if a time occurs twice
when the clocks go back, the first occurrence is used.

`status` shows a one-off status snapshot, e.g.:

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
  starting balance. The global report includes an **Away** column for
  vacation and sick leave (see [Away time](#away-time)).

### Live status view

Use `watch` to keep the status view running in a small shell window:

```sh
time-tracker watch          # uses the default project when starting
time-tracker watch web      # starts 'web' when idle
```

The current session's elapsed time is shown as a large block clock, so it is
easy to read from across the room:

```
╭──────────────────────── Elapsed ─────────────────────────╮
│             █ █    █  ███   ███ ███                      │
│             █ █ █  █  █ █ █   █   █                      │
│             ███    █  █ █   ███ ███                      │
│               █ █  █  █ █ █ █   █                        │
│               █    █  ███   ███ ███                      │
│                                                          │
│             running 'web' — started 09:12:34             │
╰──────────────────────────────────────────────────────────╯
Today  : 4:10 worked / 8:00 target
Delta  : -3:50 vs today's target
Flex   : +1:30 overall

[space] pause  [x] stop  [q] quit
```

The clock counts actual worked time, excluding pauses. It freezes while the
session is paused and shows `IDLE` when no session is active. In a very narrow
window the block clock falls back to a compact one-line display.

It refreshes once per second and accepts single-key commands:

| Key          | Idle  | Running     | Paused      |
| ------------ | ----- | ----------- | ----------- |
| `space`      | start | pause       | resume      |
| `s`          | start | —           | —           |
| `p`          | —     | pause       | —           |
| `c`          | —     | —           | resume      |
| `x`          | —     | stop        | stop        |
| `q` / Ctrl-C | quit  | quit + stop | quit + stop |

Quitting with `q` or Ctrl-C also stops the current session, if there is one.

Worked time, delta and flex use minute-level formatting; only the running
session's `elapsed` value ticks in seconds. Changes made from another shell
(for example `time-tracker pause`) appear on the next refresh.

`watch` needs an interactive terminal. Use `status` for a one-off view in
scripts or pipes. It currently supports macOS and Linux only.

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

### Away time

Use `--vacay` or `--sick` with `log` to record a full day of leave instead of
work:

```sh
time-tracker log 2026-10-20 --vacay  # a full day of vacation
time-tracker log yesterday --sick    # a full day of sick leave
```

Leave is always a full working day: omit the duration, and the configured
workday target is recorded (so `config workday 6h30m` logs `6:30` of leave).
Passing a duration together with `--vacay` or `--sick` is rejected.

Away days appear in the global report with an **Away** column. They are
**neutral** for flex: the day's delta is `0:00` regardless of the target or
any time worked that day, so leave neither adds to nor subtracts from your
balance. Away time is not attributed to a project and does not appear in
per-project reports. `--replace` also works with leave flags, overriding any
tracked or manual time for that day.

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
An optional kind marks away time (`vacation` or `sick`) instead of worked
time. Databases created before projects existed are migrated automatically.

## Development

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for development setup and how
the single-file distribution is built.
