# Contributing

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

## Development

```sh
uv sync              # install dependencies (including dev group)
uv run pytest        # run tests
uv run ruff check .  # lint
uv run ruff format . # format
```

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
