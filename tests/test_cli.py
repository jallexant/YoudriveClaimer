import logging

from youdrive.cli.main import main
from youdrive.logging_config import JsonFormatter


def test_local_commands_empty_database(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    monkeypatch.setenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "3")
    for command in ["init", "trips", "candidates", "status"]:
        assert main([command]) == 0
    output = capsys.readouterr()
    assert "Trajets : 0" in output.out
    assert "Budget d'envoi restant aujourd'hui : 3/3" in output.out
    assert "cli.completed" in output.err


def test_sync_explicitly_unavailable_without_creating_database(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(db_path))
    assert main(["sync"]) == 2
    assert "aucun endpoint" in capsys.readouterr().err
    assert not db_path.exists()


def test_invalid_config_does_not_print_raw_value(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "fake-sensitive-value")
    assert main(["status"]) == 2
    output = capsys.readouterr()
    assert "fake-sensitive-value" not in output.err
    assert "entier positif" in output.err


def test_log_formatter_does_not_include_exception_payload():
    record = logging.LogRecord("youdrive", logging.ERROR, "", 0, "database.failed", (), None)
    record.exc_info = (ValueError, ValueError("fake-secret"), None)
    assert "fake-secret" not in JsonFormatter().format(record)
