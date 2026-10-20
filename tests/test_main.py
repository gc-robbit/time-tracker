from time_tracker import main


def test_main_runs(capsys) -> None:
    main()
    captured = capsys.readouterr()
    assert "Hello from time-tracker!" in captured.out
