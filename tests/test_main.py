from time_tracker import main


def test_entrypoint_shows_status(capsys, tmp_path, monkeypatch) -> None:
    """Smoke test for the `time-tracker` console-script entry point."""
    monkeypatch.setenv("TIME_TRACKER_DB", str(tmp_path / "entry.db"))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Status" in out
