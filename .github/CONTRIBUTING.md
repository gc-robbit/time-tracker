# Contributing

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

## What you may contribute

- **Bug fixes** — please raise an issue first.
- **Features** — please raise an issue first.
- **Documentation improvements** — always welcome.

Features are accepted if they align with the minimalist / simplicity intent
of this little project.

## Development

```sh
uv sync              # install dependencies (including dev group)
uv run pytest        # run tests
uv run ruff check .  # lint
uv run ruff format . # format
```

## Commit hooks

The repo uses [prek](https://github.com/j178/prek), a fast drop-in
replacement for pre-commit, to enforce the commit message rules below. After
`uv sync`, install the hooks once:

```sh
uv run prek install -t commit-msg
```

This installs a `commit-msg` hook (see
[`prek.toml`](../prek.toml)) that rejects messages
not following Conventional Commits. Skip it for a single commit with
`git commit --no-verify`.

Dependabot cannot update the pinned hook revisions: its `pre-commit`
ecosystem only reads `.pre-commit-config.yaml`, and support for `prek.toml`
is not shipped yet ([dependabot-core#14624](https://github.com/dependabot/dependabot-core/issues/14624)).
Run this instead to bump the `rev` pins in `prek.toml`:

```sh
uv run prek update        # update pinned hook revisions
uv run prek update --check # dry run: exit 1 if updates are available (usable in CI)
```

## Commit messages

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).
Pull requests with non-conforming commit messages will not be accepted.
The `commit-msg` hook checks this automatically.

```
<type>(<optional scope>): <short imperative description>
```

Common types used in this repo:

- `feat` — a new feature
- `fix` — a bug fix
- `perf` — a performance improvement
- `test` — adding or correcting tests
- `docs` — documentation only
- `refactor` — code change that neither fixes nor adds anything
- `chore` — maintenance (deps, tooling, generated files)
- `ci` — CI configuration

A body and footer are optional; breaking changes get a `!` after the type (or
a `BREAKING CHANGE:` footer). Examples from this repo:

```
feat: support projects
fix: report sqlite failures as a clean error instead of a traceback
ci: add GitHub Actions workflow (ruff + pytest)
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
