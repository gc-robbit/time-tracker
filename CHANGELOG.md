## v0.7.0 (2026-10-31)

### Feat

- default reports to the current month

### Fix

- keep the elapsed panel's right border visible

## v0.6.0 (2026-10-31)

### Feat

- add a large elapsed clock to watch view
- add live status view with keyboard controls
- support away time (#21)

## v0.5.1 (2026-10-27)

### Perf

- skip unused project aggregation in reports

## v0.5.0 (2026-10-26)

### Feat

- remember first named project as default

### Fix

- handle DST edge cases in start --at
- resolve local date offset in midnight crossing test

## v0.4.0 (2026-10-23)

### Feat

- report by default only global; add --all and --start/--end

### Fix

- keep report filtering lint-clean and cover date ranges

## v0.3.0 (2026-10-23)

### Feat

- log worked time for past days

## v0.2.0 (2026-10-23)

### Feat

- add initial flex time buffer

## v0.1.0 (2026-10-23)

### Feat

- add optional start time
- include common aliases for pause and resume
- add single-file uv distribution
- support projects
- opencode:d first implementation

### Fix

- report sqlite failures as a clean error instead of a traceback

### Perf

- cache the parsed event log and query the last event directly
