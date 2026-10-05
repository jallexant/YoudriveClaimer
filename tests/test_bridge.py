import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy import select

from youdrive.api.bridge import handler_factory
from youdrive.db.session import initialize_database, open_database
from youdrive.models import Trip


@pytest.fixture
def relay(tmp_path):
    engine, sessions = open_database(tmp_path / "relay.sqlite3")
    initialize_database(engine)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), handler_factory("fake-private-token", sessions, threading.Lock()),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/trips", sessions
    server.shutdown()
    server.server_close()
    thread.join()
    engine.dispose()


def send(url, payload, token="fake-private-token", origin="chrome-extension://" + "a" * 32):
    request = Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}",
        "Origin": origin,
    })
    with urlopen(request, timeout=2) as response:
        return response.status, json.load(response)


def rows():
    return {"source": "direct-assurance-visible-v1", "page": "history", "trips": [{
        "date": "2 octobre 2026", "start": "10:00", "end": "10:15", "score": "85",
        "distance": "8.5 km", "duration": "00:15", "identity": "f" * 64,
    }]}


def test_loopback_receives_repeat_batches_without_duplicates(relay):
    url, sessions = relay
    assert send(url, rows()) == (200, {"received": 1, "added": 1, "updated": 0})
    assert send(url, rows()) == (200, {"received": 1, "added": 0, "updated": 1})
    with sessions() as session:
        assert len(list(session.scalars(select(Trip)))) == 1


@pytest.mark.parametrize("headers", [
    {"token": "incorrect"}, {"origin": "https://untrusted.example"},
    {"origin": "null"},
])
def test_untrusted_sender_cannot_write_database(relay, headers):
    url, sessions = relay
    with pytest.raises(HTTPError) as caught:
        send(url, rows(), **headers)
    assert caught.value.code == 403
    with sessions() as session:
        assert list(session.scalars(select(Trip))) == []


def test_partial_invalid_batch_is_rejected_atomically(relay):
    url, sessions = relay
    data = rows()
    data["trips"].append({**data["trips"][0], "identity": "e" * 64, "score": "101"})
    with pytest.raises(HTTPError) as caught:
        send(url, data)
    assert caught.value.code == 400
    with sessions() as session:
        assert list(session.scalars(select(Trip))) == []
