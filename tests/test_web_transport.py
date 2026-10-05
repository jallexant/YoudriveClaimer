import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from youdrive.api import web

TRIP_URL = (
    f"{web.ORIGIN}/api/private-domain-redesign/youdrive/policy/fake-policy/trips?numberOfTrips=13"
)
OLD_STATE = {"cookies": [], "origins": []}
NEW_STATE = {"cookies": [], "origins": [{"origin": web.ORIGIN, "localStorage": []}]}


def trip_payload():
    return {"status": 0, "data": [{
        "id": "fake-trip", "startDate": "2026-10-02T10:00:00+02:00",
        "endDate": "2026-10-02T10:15:00+02:00", "score": 85,
        "distance": 8.5, "durationInMinutes": 15,
    }]}


def response_mock(status=200, payload=None):
    return SimpleNamespace(
        status=status, headers={"content-type": "application/json"}, url=TRIP_URL,
        request=SimpleNamespace(method="GET"),
        json=Mock(return_value=trip_payload() if payload is None else payload),
    )


def install_browser_mock(monkeypatch, response):
    request = SimpleNamespace(get=Mock(return_value=response))
    page = SimpleNamespace(goto=Mock(), is_closed=Mock(return_value=False),
                           wait_for_timeout=Mock())
    context = SimpleNamespace(
        request=request, storage_state=Mock(return_value=NEW_STATE), on=Mock(),
        new_page=Mock(return_value=page),
    )
    browser = SimpleNamespace(new_context=Mock(return_value=context), close=Mock())
    launch = Mock(return_value=browser)

    @contextmanager
    def playwright_context():
        yield SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    monkeypatch.setattr(web, "_playwright", lambda: playwright_context)
    return SimpleNamespace(request=request, page=page, context=context,
                           browser=browser, launch=launch)


def saved_session(tmp_path):
    path = tmp_path / "session.json"
    web._save_session(path, TRIP_URL, OLD_STATE)
    return path


def test_fetch_success_reuses_session_and_saves_refreshed_state(monkeypatch, tmp_path):
    path = saved_session(tmp_path)
    harness = install_browser_mock(monkeypatch, response_mock())

    trips = web.fetch_trips(path)

    assert len(trips) == 1
    assert trips[0].score == 85
    assert trips[0].duration_seconds == 900
    harness.browser.new_context.assert_called_once_with(storage_state=OLD_STATE)
    harness.request.get.assert_called_once_with(TRIP_URL, timeout=60000, max_redirects=0)
    harness.launch.assert_called_once_with(channel="chrome", headless=True)
    harness.browser.close.assert_called_once()
    assert json.loads(path.read_text(encoding="utf-8"))["storage_state"] == NEW_STATE


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 403, 503])
def test_fetch_refusal_never_saves_session(monkeypatch, tmp_path, status):
    path = saved_session(tmp_path)
    original = path.read_bytes()
    response = response_mock(status=status)
    harness = install_browser_mock(monkeypatch, response)

    with pytest.raises(web.WebError):
        web.fetch_trips(path)

    assert path.read_bytes() == original
    harness.context.storage_state.assert_not_called()
    response.json.assert_not_called()
    harness.browser.close.assert_called_once()


def test_fetch_changed_schema_never_saves_session(monkeypatch, tmp_path):
    path = saved_session(tmp_path)
    original = path.read_bytes()
    payload = trip_payload()
    del payload["data"][0]["startDate"]
    harness = install_browser_mock(monkeypatch, response_mock(payload=payload))

    with pytest.raises(web.WebError, match="Schéma"):
        web.fetch_trips(path)

    assert path.read_bytes() == original
    harness.context.storage_state.assert_not_called()
    harness.browser.close.assert_called_once()


def test_login_invalid_session_starts_fresh_and_replaces_only_after_success(monkeypatch, tmp_path):
    path = tmp_path / "session.json"
    original = b"invalid json"
    path.write_bytes(original)
    response = response_mock()
    harness = install_browser_mock(monkeypatch, response)

    def visit_dashboard(*args, **kwargs):
        assert path.read_bytes() == original
        event, callback = harness.context.on.call_args.args
        assert event == "response"
        callback(response)

    harness.page.goto.side_effect = visit_dashboard

    trips = web.login(path)

    assert len(trips) == 1
    harness.browser.new_context.assert_called_once_with(
        storage_state=None, locale="fr-FR", timezone_id="Europe/Paris",
    )
    harness.launch.assert_called_once_with(channel="chrome", headless=False)
    harness.browser.close.assert_called_once()
    assert json.loads(path.read_text(encoding="utf-8"))["storage_state"] == NEW_STATE


def test_login_invalid_session_retains_original_when_connection_fails(monkeypatch, tmp_path):
    path = tmp_path / "session.json"
    original = b"invalid json"
    path.write_bytes(original)
    harness = install_browser_mock(monkeypatch, response_mock())

    with pytest.raises(web.WebError, match="délai"):
        web.login(path, timeout_seconds=0)

    assert path.read_bytes() == original
    harness.context.storage_state.assert_not_called()
    harness.browser.close.assert_called_once()


def test_fetch_invalid_session_still_refuses_before_browser(monkeypatch, tmp_path):
    path = tmp_path / "session.json"
    path.write_text("invalid json", encoding="utf-8")
    playwright = Mock(side_effect=AssertionError("Browser must not be opened"))
    monkeypatch.setattr(web, "_playwright", playwright)

    with pytest.raises(web.WebError, match="Session locale invalide"):
        web.fetch_trips(path)

    playwright.assert_not_called()
