import pytest

from time_tracker.cli import main


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


def test_config_missing_value(capsys) -> None:
    assert main(["config", "workday"]) == 1
    assert "missing value" in capsys.readouterr().err


def test_corrupt_db_reports_clean_error(tmp_path, capsys) -> None:
    (tmp_path / "cli.db").write_bytes(b"this is not a sqlite database")
    assert main(["status"]) == 1
    err = capsys.readouterr().err
    assert "Database error" in err
    assert "Traceback" not in err
