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

`tools/build_dist.py` renders the package into a standalone copy of this
project as a single [PEP 723](https://peps.python.org/pep-0723/) script with
inline `uv` metadata. It only uses the Python standard library, so anyone with
[uv](https://docs.astral.sh/uv/) can run it from anywhere — no clone, no
install:

```sh
./time-tracker start web       # shebang runs uv for you
uv run --script time-tracker status
```

The file has no `.py` extension on purpose: it can be copied or renamed freely
(e.g. onto your `PATH` as `time-tracker`) and keeps working, because the
`--script` flag lives in its shebang. Note that plain `uv run time-tracker`
won't be recognized as a script — pass `--script`.

The file is a build output and is **not committed**: `src/time_tracker/` is the
only source of truth. Build it locally with:

```sh
uv run tools/build_dist.py          # write dist/time-tracker
uv run tools/build_dist.py --check  # verify an existing file is up to date
```

Downloaded release assets do not keep the executable bit, so run
`chmod +x time-tracker` once after downloading.

## Dependabot updates

Dependabot proposes weekly updates for Python dependencies and GitHub Actions.
A workflow approves minor and patch updates and enables auto-merge, so they
land once CI passes and the PR is up to date with `main`. Major updates are
left for manual review.

The workflow uses a dedicated fine-grained PAT stored as the Dependabot secret
`DEPENDABOT_AUTOMERGE_TOKEN`. Scope it to this repository with **Contents: read
and write**, **Pull requests: read and write**, and **Workflows: read and
write**, then add it with:

```sh
gh secret set DEPENDABOT_AUTOMERGE_TOKEN --app dependabot
```

Dependabot PRs cannot read Actions secrets, and `GITHUB_TOKEN` can never merge
a change under `.github/workflows/`, so an Actions secret or the default token
would leave GitHub Actions bumps stuck after CI passes. The workflow itself
never checks out PR code and pins `dependabot/fetch-metadata` to a commit SHA.

## Releases

Releases are cut manually from the **Release** workflow (`workflow_dispatch`).
It runs [`cz bump`](https://commitizen-tools.github.io/commitizen/), which
derives the next version from the Conventional Commits since the last tag,
updates `pyproject.toml` and `uv.lock`, regenerates `CHANGELOG.md`, and commits
and tags the bump. The workflow then builds `dist/time-tracker` and attaches it
to a GitHub release.

Versioning follows the commit types: `fix` → patch, `feat` → minor, and
breaking changes → major (minor while the project is below 1.0.0). A run with
no bump-eligible commits fails instead of releasing anything.

The workflow authenticates with the `RELEASE_TOKEN` repository secret — a
fine-grained personal access token with **Contents: read and write**. A PAT is
required because `GITHUB_TOKEN` cannot bypass the `main` ruleset that requires
pull requests.
