"""Tests for the single-file distribution built by tools/build_dist.py."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "tools" / "build_dist.py"


def _run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, check=False, **kwargs
    )


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the distribution once into a temporary directory."""
    output = tmp_path_factory.mktemp("dist") / "time-tracker"
    result = _run([sys.executable, str(GENERATOR), "--output", str(output)])
    assert result.returncode == 0, result.stderr
    return output


def test_check_reports_freshness(dist: Path, tmp_path: Path) -> None:
    """--check accepts an up-to-date file and rejects a stale one."""
    result = _run([sys.executable, str(GENERATOR), "--check", "-o", str(dist)])
    assert result.returncode == 0, result.stderr

    stale = tmp_path / "time-tracker"
    stale.write_text("stale\n")
    result = _run([sys.executable, str(GENERATOR), "--check", "-o", str(stale)])
    assert result.returncode == 1
    assert "is out of date" in result.stderr


def test_dist_has_uv_script_header(dist: Path) -> None:
    text = dist.read_text()
    assert text.startswith("#!/usr/bin/env -S uv run --script\n# /// script\n")
    assert 'requires-python = ">=3.11"' in text
    assert "dependencies = []" in text
    assert text.rstrip().endswith("sys.exit(main())")
    assert os.access(dist, os.X_OK), "the distribution must be executable"


def test_dist_smoke_flow(dist: Path, tmp_path: Path) -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ | {"TIME_TRACKER_DB": str(tmp_path / "dist.db")}
        return _run([sys.executable, str(dist), *args], env=env)

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
    assert "Project: web" not in result.stdout
    assert "Flex (global):" in result.stdout
    result = run("report", "--all")
    assert result.returncode == 0
    assert "Project: web" in result.stdout
    assert "Flex (global):" in result.stdout
