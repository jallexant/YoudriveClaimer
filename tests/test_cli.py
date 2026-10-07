import logging
from datetime import UTC, datetime

import pytest

from youdrive.cli.main import main
from youdrive.config import Settings
from youdrive.db.session import open_database
from youdrive.logging_config import JsonFormatter
from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import PhoneTrip
from youdrive.services.trips import remaining_draft_budget


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


def test_sync_stops_on_phone_error_without_importing(monkeypatch, tmp_path, capsys):
    def fail(*_args):
        raise PhoneError("Téléphone USB introuvable.")

    monkeypatch.setattr("youdrive.cli.main.collect_trips", fail)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    assert main(["sync"]) == 2
    assert "Téléphone USB introuvable" in capsys.readouterr().err
    assert main(["trips"]) == 0
    assert "Aucun trajet." in capsys.readouterr().out


def test_full_sync_ignores_known_trips(monkeypatch, tmp_path, capsys):
    received = []

    def collect(_adb, _tz, _sleep, _shots, known):
        received.append(known)
        return [], False

    monkeypatch.setattr("youdrive.cli.main.collect_trips", collect)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    assert main(["sync", "--full"]) == 0
    assert received == [set()]
    assert "Fin de la liste atteinte." in capsys.readouterr().out


def test_sync_imports_the_phone_batch(monkeypatch, tmp_path, capsys):
    trip = PhoneTrip(
        "phone:abc", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 8, 30, tzinfo=UTC),
        80, 12.5, 1800, "adresse privée", "autre adresse privée",
    )
    monkeypatch.setattr("youdrive.cli.main.collect_trips", lambda *_args: ([trip], False))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    assert main(["sync"]) == 0
    output = capsys.readouterr().out
    assert "nouveaux : 1" in output
    assert "USB" in output
    assert "adresse privée" not in output
    assert "Aucune réclamation envoyée." in output


def test_mark_claimed_removes_older_candidates_without_using_the_draft_budget(
    monkeypatch, tmp_path, capsys,
):
    def trip(remote_id: str, start: datetime) -> PhoneTrip:
        return PhoneTrip(remote_id, start, start.replace(minute=30), 70, 5, 1800, "a", "b")

    batch = [
        trip("phone:old", datetime(2026, 9, 30, 8, tzinfo=UTC)),
        trip("phone:new", datetime(2026, 10, 1, 8, tzinfo=UTC)),
    ]
    monkeypatch.setattr("youdrive.cli.main.collect_trips", lambda *_args: (batch, False))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    monkeypatch.setenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "3")
    assert main(["sync"]) == 0
    capsys.readouterr()
    assert main(["mark-claimed", "--before", "2026-10-01"]) == 0
    assert "déjà réclamés : 1." in capsys.readouterr().out
    assert main(["candidates"]) == 0
    output = capsys.readouterr().out
    assert "2026-10-01" in output
    assert "2026-09-30" not in output
    settings = Settings.from_env()
    engine, sessions = open_database(settings.db_path)
    with sessions() as session:
        assert remaining_draft_budget(session, settings, datetime.now(UTC)) == 3
    engine.dispose()


def test_mark_claimed_requires_a_date(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    with pytest.raises(SystemExit):
        main(["mark-claimed"])


def test_drafts_command_reports_creation_without_sending(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "cli.sqlite3"))
    monkeypatch.setenv("YOUDRIVE_CONTRACT_NUMBER", "000")
    assert main(["init"]) == 0
    monkeypatch.setattr(
        "youdrive.claims.drafts.prepare_drafts", lambda *_args: 1,
    )
    assert main(["drafts"]) == 0
    output = capsys.readouterr().out
    assert "Brouillons créés : 1." in output
    assert "Aucun message envoyé." in output
    assert "000" not in output


def test_gmail_login_does_not_echo_the_client_path(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    secret = tmp_path / "secret-client.json"
    monkeypatch.setenv("YOUDRIVE_GMAIL_CLIENT_FILE", str(secret))
    assert main(["gmail-login"]) == 2
    assert "secret-client" not in capsys.readouterr().err


def test_removed_commands_are_rejected():
    for command in ("login", "auth-callback", "browser-setup"):
        with pytest.raises(SystemExit) as caught:
            main([command])
        assert caught.value.code == 2


def test_invalid_config_does_not_print_raw_value(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "fake-sensitive-value")
    assert main(["status"]) == 2
    output = capsys.readouterr()
    assert "fake-sensitive-value" not in output.err
    assert "entier positif" in output.err


def test_ui_command_opens_the_screen(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    called = []
    monkeypatch.setattr("youdrive.ui.app.run_ui", lambda: called.append("ui") or 0)
    assert main(["ui"]) == 0
    assert called == ["ui"]


def test_log_formatter_does_not_include_exception_payload():
    record = logging.LogRecord("youdrive", logging.ERROR, "", 0, "database.failed", (), None)
    record.exc_info = (ValueError, ValueError("fake-secret"), None)
    assert "fake-secret" not in JsonFormatter().format(record)
