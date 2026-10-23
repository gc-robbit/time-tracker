from datetime import datetime, timedelta

import pytest

from time_tracker.cli import main


def _day(days_ago: int = 0) -> str:
    return (datetime.now().astimezone().date() - timedelta(days=days_ago)).isoformat()


@pytest.fixture(autouse=True)
def cli_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TIME_TRACKER_DB", str(tmp_path / "cli.db"))


def test_no_args_shows_status(capsys) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Status" in out
    assert "idle" in out


def test_full_flow(capsys) -> None:
    assert main(["start", "web"]) == 0
    assert "Started 'web' at" in capsys.readouterr().out

    assert main(["status"]) == 0
    status = capsys.readouterr().out
    assert "running" in status
    assert "web" in status

    assert main(["pause"]) == 0
    assert "Paused at" in capsys.readouterr().out

    assert main(["status"]) == 0
    assert "paused" in capsys.readouterr().out

    assert main(["continue"]) == 0
    assert "Resumed at" in capsys.readouterr().out

    assert main(["pause"]) == 0
    capsys.readouterr()
    assert main(["resume"]) == 0
    assert "Resumed at" in capsys.readouterr().out

    for alias in ("lunch", "out"):
        assert main([alias]) == 0
        assert "Paused at" in capsys.readouterr().out
        assert main(["back"]) == 0
        assert "Resumed at" in capsys.readouterr().out

    assert main(["stop"]) == 0
    out = capsys.readouterr().out
    assert "Stopped at" in out
    assert "Session 'web' worked" in out

    assert main(["status"]) == 0
    assert "idle" in capsys.readouterr().out


def test_double_start_fails(capsys) -> None:
    assert main(["start", "web"]) == 0
    capsys.readouterr()
    assert main(["start", "web"]) == 1
    assert "already running" in capsys.readouterr().err


def test_stop_when_idle_fails(capsys) -> None:
    assert main(["stop"]) == 1
    assert "nothing to stop" in capsys.readouterr().err


def test_pause_when_idle_fails(capsys) -> None:
    assert main(["pause"]) == 1
    assert "Nothing to pause" in capsys.readouterr().err


def test_report_with_no_data(capsys) -> None:
    assert main(["report"]) == 0
    assert "No time tracked yet" in capsys.readouterr().out


def test_report_after_tracking(capsys) -> None:
    assert main(["start", "web"]) == 0
    assert main(["stop"]) == 0
    capsys.readouterr()
    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "Project: web" in out
    assert "Flex (global):" in out
    assert "Balance" in out


def test_start_at_specific_time(capsys) -> None:
    assert main(["start", "web", "--at", "00:00"]) == 0
    out = capsys.readouterr().out
    assert "Started 'web' at 00:00:00" in out

    assert main(["stop"]) == 0


def test_start_at_invalid_time_fails(capsys) -> None:
    assert main(["start", "web", "--at", "25:00"]) == 1
    assert "invalid time" in capsys.readouterr().err


def test_start_without_project_fails(capsys) -> None:
    assert main(["start"]) == 1
    err = capsys.readouterr().err
    assert "no project given" in err
    assert "default_project" in err


def test_default_project_is_used_when_omitted(capsys) -> None:
    assert main(["config", "default_project", "web"]) == 0
    capsys.readouterr()

    assert main(["start"]) == 0
    assert "Started 'web' at" in capsys.readouterr().out
    assert main(["stop"]) == 0


def test_explicit_project_overrides_default(capsys) -> None:
    assert main(["config", "default_project", "web"]) == 0
    capsys.readouterr()

    assert main(["start", "design"]) == 0
    assert "Started 'design' at" in capsys.readouterr().out
    assert main(["stop"]) == 0


def test_report_per_project(capsys) -> None:
    assert main(["start", "web"]) == 0
    assert main(["stop"]) == 0
    assert main(["start", "design"]) == 0
    assert main(["stop"]) == 0
    capsys.readouterr()

    assert main(["report", "web"]) == 0
    out = capsys.readouterr().out
    assert "web" in out
    assert "design" not in out
    assert "Flex" not in out

    assert main(["report", "nope"]) == 0
    assert "No time tracked for project 'nope'" in capsys.readouterr().out

    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "Project: web" in out
    assert "Project: design" in out


def test_config_show_includes_default_project(capsys) -> None:
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "8h" in out
    assert "Initial flex buffer: +0:00" in out
    assert "(not set)" in out

    assert main(["config", "default_project", "web"]) == 0
    capsys.readouterr()
    assert main(["config"]) == 0
    assert "Default project: web" in capsys.readouterr().out


def test_config_empty_default_project(capsys) -> None:
    assert main(["config", "default_project", " "]) == 1
    assert "must not be empty" in capsys.readouterr().err


def test_config_show_and_set(capsys) -> None:
    assert main(["config"]) == 0
    assert "8h" in capsys.readouterr().out

    assert main(["config", "workday", "6h30m"]) == 0
    assert "6h30m" in capsys.readouterr().out

    assert main(["config"]) == 0
    assert "6h30m" in capsys.readouterr().out


def test_config_invalid_duration(capsys) -> None:
    assert main(["config", "workday", "banana"]) == 1
    assert "invalid duration" in capsys.readouterr().err


def test_config_flex_buffer(capsys) -> None:
    assert main(["config", "flex_buffer", "1h30m"]) == 0
    assert "Initial flex buffer set to +1:30." in capsys.readouterr().out

    assert main(["config"]) == 0
    assert "Initial flex buffer: +1:30" in capsys.readouterr().out

    assert main(["config", "flex_buffer", "-2h"]) == 0
    assert "Initial flex buffer set to -2:00." in capsys.readouterr().out

    assert main(["config"]) == 0
    assert "Initial flex buffer: -2:00" in capsys.readouterr().out


def test_config_invalid_flex_buffer(capsys) -> None:
    assert main(["config", "flex_buffer", "banana"]) == 1
    assert "invalid duration" in capsys.readouterr().err


def test_flex_buffer_in_status_and_report(capsys) -> None:
    assert main(["config", "flex_buffer", "2h"]) == 0
    capsys.readouterr()

    assert main(["status"]) == 0
    assert "Flex   : +2:00 overall" in capsys.readouterr().out

    assert main(["start", "web"]) == 0
    assert main(["stop"]) == 0
    capsys.readouterr()

    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "Starting balance: +2:00" in out


def test_config_missing_value(capsys) -> None:
    assert main(["config", "workday"]) == 1
    assert "missing value" in capsys.readouterr().err


def test_log_manual_day_and_report(capsys) -> None:
    day = _day(1)
    assert main(["log", day, "7h30m", "web"]) == 0
    out = capsys.readouterr().out
    assert f"Logged 7:30 for 'web' on {day}" in out
    assert "day total 7:30" in out

    assert main(["log", day, "30m", "web"]) == 0
    assert "day total 8:00" in capsys.readouterr().out

    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "Project: web" in out
    assert day in out
    assert "8:00" in out


def test_log_uses_default_project(capsys) -> None:
    assert main(["config", "default_project", "web"]) == 0
    capsys.readouterr()

    day = _day(2)
    assert main(["log", day, "8h"]) == 0
    assert f"Logged 8:00 for 'web' on {day}" in capsys.readouterr().out


def test_log_accepts_relative_dates(capsys) -> None:
    assert main(["log", "yesterday", "8h", "web"]) == 0
    assert _day(1) in capsys.readouterr().out

    assert main(["log", "today", "1h", "web"]) == 0
    assert _day() in capsys.readouterr().out


def test_log_replace_overrides_the_day(capsys) -> None:
    day = _day(3)
    assert main(["log", day, "8h", "web"]) == 0
    capsys.readouterr()

    assert main(["log", day, "7h", "design", "--replace"]) == 0
    out = capsys.readouterr().out
    assert f"Replaced all time on {day} with 7:00 for 'design'" in out
    assert "day total 7:00" in out

    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "Project: design" in out
    assert "Project: web" not in out


def test_log_without_project_only_affects_global_flex(capsys) -> None:
    day = _day(4)
    assert main(["log", day, "8h"]) == 0
    capsys.readouterr()

    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "No time tracked yet" not in out
    assert "Flex (global):" in out
    assert "Project:" not in out


def test_log_rejects_invalid_input(capsys) -> None:
    assert main(["log", "not-a-date", "8h"]) == 1
    assert "invalid date" in capsys.readouterr().err

    assert main(["log", _day(-1), "8h"]) == 1
    assert "future" in capsys.readouterr().err

    assert main(["log", _day(), "0h"]) == 1
    assert "at least one minute" in capsys.readouterr().err

    assert main(["log", _day(), "banana"]) == 1
    assert "invalid duration" in capsys.readouterr().err


def test_corrupt_db_reports_clean_error(tmp_path, capsys) -> None:
    (tmp_path / "cli.db").write_bytes(b"this is not a sqlite database")
    assert main(["status"]) == 1
    err = capsys.readouterr().err
    assert "Database error" in err
    assert "Traceback" not in err
