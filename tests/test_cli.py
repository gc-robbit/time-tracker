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
    assert main(["start"]) == 0
    assert "Started at" in capsys.readouterr().out

    assert main(["status"]) == 0
    assert "running" in capsys.readouterr().out

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

    assert main(["stop"]) == 0
    out = capsys.readouterr().out
    assert "Stopped at" in out
    assert "Session worked" in out

    assert main(["status"]) == 0
    assert "idle" in capsys.readouterr().out


def test_double_start_fails(capsys) -> None:
    assert main(["start"]) == 0
    capsys.readouterr()
    assert main(["start"]) == 1
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
    assert main(["start"]) == 0
    assert main(["stop"]) == 0
    capsys.readouterr()
    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "Date" in out
    assert "Balance" in out


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
