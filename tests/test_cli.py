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


def test_sync_stops_on_android_error_without_creating_database(monkeypatch, tmp_path, capsys):
    from youdrive.api.android import AndroidError

    def fail(_settings):
        raise AndroidError("Session refusée.")

    monkeypatch.setattr("youdrive.cli.main.synchronize", fail)
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(db_path))
    assert main(["sync"]) == 2
    assert "Session refusée" in capsys.readouterr().err
    assert not db_path.exists()


def test_sync_imports_the_android_batch(monkeypatch, tmp_path, capsys):
    from datetime import UTC, datetime

    from youdrive.api.android import AndroidTrip, SyncBatch

    trip = AndroidTrip(
        "android:2026-06-01T10:00:00", datetime(2026, 6, 1, 8, tzinfo=UTC),
        datetime(2026, 6, 1, 8, 30, tzinfo=UTC), 80, 12.5, 1800, [{"kind": "fiction"}], None,
    )
    monkeypatch.setattr("youdrive.cli.main.synchronize", lambda _settings: SyncBatch([trip], 1))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    assert main(["sync"]) == 0
    output = capsys.readouterr().out
    assert "nouveaux : 1" in output
    assert "liste complète" in output
    assert "fiction" not in output


def test_login_command_reports_that_the_password_is_not_stored(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("youdrive.cli.main.login", lambda _settings: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    assert main(["login"]) == 0
    assert "mot de passe" in capsys.readouterr().out


def test_web_collection_commands_are_gone():
    import pytest
    with pytest.raises(SystemExit) as caught:
        main(["browser-setup"])
    assert caught.value.code == 2


def test_auth_callback_writes_only_the_official_return(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    rejected = main([
        "auth-callback", "https://evil.example/?code=fiction", "--directory", str(tmp_path),
    ])
    assert rejected == 2
    assert "fiction" not in capsys.readouterr().err
    accepted = main([
        "auth-callback", "fr.axa.youdrive://auth?code=fiction", "--directory", str(tmp_path),
    ])
    assert accepted == 0
    assert (tmp_path / "android-login-callback.txt").read_text(encoding="utf-8").endswith("fiction")


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
