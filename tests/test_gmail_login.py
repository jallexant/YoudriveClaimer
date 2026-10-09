import webbrowser

import pytest

from youdrive.claims.errors import GmailError
from youdrive.claims.gmail import login
from youdrive.config import Settings
from youdrive.ui.present import google_auth_url


class _Creds:
    def to_json(self) -> str:
        return '{"token":"test"}'


def _settings(tmp_path) -> Settings:
    client = tmp_path / "client.json"
    client.write_text("{}", encoding="utf-8")
    return Settings(db_path=tmp_path / "youdrive.sqlite3", gmail_client_file=client)


def _install(monkeypatch, run_local_server) -> None:
    class FakeFlow:
        @classmethod
        def from_client_secrets_file(cls, path, scopes):
            assert "https://www.googleapis.com/auth/gmail.modify" in scopes
            return cls()

        def run_local_server(self, **kwargs):
            return run_local_server(self, **kwargs)

    import google_auth_oauthlib.flow as flow_mod

    monkeypatch.setattr(flow_mod, "InstalledAppFlow", FakeFlow)


def test_login_gives_the_google_page_to_the_screen(monkeypatch, tmp_path, capsys):
    seen = {}
    handed = []

    def run_local_server(self, **kwargs):
        seen.update(kwargs)
        webbrowser.get(kwargs["browser"]).open(
            "https://accounts.google.com/o/oauth2/v2/auth?x=1",
        )
        return _Creds()

    _install(monkeypatch, run_local_server)
    original = webbrowser.get

    def guarded(using=None):
        if using != "youdrive-gmail":
            raise AssertionError(using)
        return original(using)

    monkeypatch.setattr(webbrowser, "get", guarded)
    settings = _settings(tmp_path)
    login(settings, on_url=handed.append)
    assert handed == ["https://accounts.google.com/o/oauth2/v2/auth?x=1"]
    assert seen["browser"] == "youdrive-gmail"
    assert seen["open_browser"] is True
    assert seen["prompt"] == "consent"
    assert seen["timeout_seconds"] == 300
    assert seen["authorization_prompt_message"] == ""
    assert "fermer cette fenêtre" in seen["success_message"]
    assert (tmp_path / "gmail-token.json").read_text(encoding="utf-8") == '{"token":"test"}'
    assert capsys.readouterr().out == ""


def test_login_prints_the_page_when_nothing_is_waiting_for_it(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("youdrive.claims.gmail._interactive_session", lambda: False)

    def run_local_server(self, **kwargs):
        webbrowser.get(kwargs["browser"]).open(
            "https://accounts.google.com/o/oauth2/v2/auth?x=1",
        )
        return _Creds()

    _install(monkeypatch, run_local_server)
    login(_settings(tmp_path))
    output = capsys.readouterr().out
    assert "https://accounts.google.com/o/oauth2/v2/auth?x=1" in output


def test_login_reports_a_missed_confirmation(monkeypatch, tmp_path):
    from google_auth_oauthlib.flow import WSGITimeoutError

    def run_local_server(self, **kwargs):
        raise WSGITimeoutError("late")

    _install(monkeypatch, run_local_server)
    with pytest.raises(GmailError, match="confirmée"):
        login(_settings(tmp_path), on_url=lambda _url: None)


def test_login_hides_an_unexpected_refusal(monkeypatch, tmp_path):
    def run_local_server(self, **kwargs):
        raise RuntimeError("denied")

    _install(monkeypatch, run_local_server)
    with pytest.raises(GmailError, match="refusée"):
        login(_settings(tmp_path), on_url=lambda _url: None)


def test_google_auth_url_rejects_anything_else():
    page = "https://accounts.google.com/o/oauth2/v2/auth?x=1"
    assert google_auth_url(page) == page
    assert google_auth_url("https://evil.example/accounts.google.com/") == ""
    assert google_auth_url("javascript:alert(1)") == ""
    assert google_auth_url(page + " x") == ""
