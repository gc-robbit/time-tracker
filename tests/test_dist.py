"""Tests for the generated single-file distribution (dist/time-tracker)."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "tools" / "build_dist.py"
DIST = REPO_ROOT / "dist" / "time-tracker"


def _run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, check=False, **kwargs
    )


def test_dist_is_up_to_date() -> None:
    """The committed distribution must match the package sources."""
    result = _run([sys.executable, str(GENERATOR), "--check"])
    assert result.returncode == 0, (
        "dist/time-tracker is stale — run 'uv run tools/build_dist.py'\n"
        f"{result.stdout}{result.stderr}"
    )


def test_dist_has_uv_script_header() -> None:
    text = DIST.read_text()
    assert text.startswith("#!/usr/bin/env -S uv run --script\n# /// script\n")
    assert 'requires-python = ">=3.11"' in text
    assert "dependencies = []" in text
    assert text.rstrip().endswith("sys.exit(main())")
    assert os.access(DIST, os.X_OK), "dist/time-tracker must be executable"


def test_dist_smoke_flow(tmp_path: Path) -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ | {"TIME_TRACKER_DB": str(tmp_path / "dist.db")}
        return _run([sys.executable, str(DIST), *args], env=env)

    # A project is still required when no default is configured.
    result = run("start")
    assert result.returncode == 1
    assert "no project given" in result.stderr

    assert run("config", "default_project", "web").returncode == 0

    result = run("start")
    assert result.returncode == 0, result.stderr
    assert "Started 'web' at" in result.stdout

    result = run("status")
    assert result.returncode == 0
    assert "running" in result.stdout
    assert "web" in result.stdout

    result = run("stop")
    assert result.returncode == 0
    assert "Session 'web' worked" in result.stdout

    result = run("report")
    assert result.returncode == 0
    assert "Project: web" in result.stdout
    assert "Flex (global):" in result.stdout
