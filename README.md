# time-tracker

A time tracking application.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```sh
uv sync            # install dependencies (including dev group)
uv run time-tracker  # run the app
uv run pytest      # run tests
uv run ruff check .  # lint
uv run ruff format .  # format
```
