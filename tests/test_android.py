import json
import zipfile
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from youdrive.api.android import (
    AUTH_ORIGIN,
    AndroidError,
    AndroidTrip,
    _authorization_code,
    _client_id,
    _RejectRedirect,
    accept_callback,
    build_authorize_url,
    parse_trips,
    pkce_pair,
    policy_ids,
    synchronize,
    trips_path,
)
from youdrive.config import Settings
from youdrive.models import Claim, ClaimStatus, Trip
from youdrive.services.sync import import_android_trips

# The production constant is private to the module; tests patch the path only.
_ENV_NAME = "assets/flutter_assets/assets/env/.env.production"


def _trip(start: str, **extra) -> dict:
    stop = extra.pop("stop_time", start.replace("T10:00:00", "T10:30:00"))
    payload = {
        "distance": 12.5,
        "end_location": {"address": "arrivee-fiction"},
        "score": 80,
        "status": "ok",
        "status_detail": "fiction",
        "start_location": {"address": "depart-fiction"},
        "start_time": start,
        "stop_time": stop,
        "scores_dil": {"acceleration": 1, "braking": 2, "expert": 3, "smoothness": 4},
        "poi_dil": [{"kind": "fiction"}],
    }
    payload.update(extra)
    return payload


def _settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "app.sqlite3")


def _save_session(settings: Settings, refresh: str = "refresh-fiction",
                 when: str = "2099-01-01T00:00:00+00:00") -> None:
    path = settings.db_path.parent / "android-session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "access_token": "access-fiction",
        "refresh_token": refresh,
        "expires_at": when,
    }), encoding="utf-8")


def test_trips_path_has_no_page_parameter():
    path = trips_path("policy/fiction")
    assert path.startswith("/users/trips?")
    assert "with_pois=true" in path
    assert path.endswith("&with_invalid=true")
    assert "encrypted_policy_id=policy%2Ffiction" in path
    assert "page=" not in path
    assert "numberOfTrips" not in path


def test_parse_keeps_distance_and_eleven_trips():
    trips = parse_trips(
        {"trips": [_trip(f"2026-06-{day:02d}T10:00:00") for day in range(1, 12)]},
        "Europe/Paris",
    )
    assert len(trips) == 11
    assert trips[0].remote_id == "android:2026-06-01T10:00:00"
    assert trips[0].started_at == datetime(2026, 6, 1, 8, tzinfo=UTC)
    assert trips[0].duration_seconds == 1800
    assert trips[0].distance_km == 12.5
    assert trips[0].events == [{"kind": "fiction"}]
    assert trips[0].gps["scores"]["braking"] == 2


def test_aware_timestamp_and_raw_large_distance():
    raw = {"trips": [_trip(
        "2026-06-01T08:00:00Z", distance=12500, stop_time="2026-06-01T08:30:00Z",
    )]}
    trip, = parse_trips(raw, "Europe/Paris")
    assert trip.started_at == datetime(2026, 6, 1, 8, tzinfo=UTC)
    assert trip.distance_km == 12500


@pytest.mark.parametrize("start", ["2026-10-25T02:30:00", "2026-03-29T02:30:00"])
def test_ambiguous_or_missing_paris_hour_rejects_the_batch(start):
    with pytest.raises(AndroidError, match="ambigu ou inexistant"):
        parse_trips({"trips": [_trip(start, stop_time="2026-06-01T10:30:00")]}, "Europe/Paris")


@pytest.mark.parametrize("payload", [
    {},
    {"trips": {}},
    {"trips": ["fiction"]},
    {"hasNextPage": True, "trips": [_trip("2026-06-01T10:00:00")]},
    {"trips": [_trip("2026-06-01T10:00:00", score=101)]},
    {"trips": [_trip("2026-06-01T10:00:00", score=True)]},
    {"trips": [_trip("2026-06-01T10:00:00", distance=-1)]},
    {"trips": [_trip("2026-06-01T10:00:00", stop_time="2026-06-01T09:00:00")]},
    {"trips": [_trip("2026-06-01T10:00:00"), _trip("2026-06-01T10:00:00")]},
    {"trips": [_trip("2026-06-01T10:00:00", poi_dil=["fiction"])]},
])
def test_bad_schema_rejects_without_echoing_values(payload):
    with pytest.raises(AndroidError) as caught:
        parse_trips(payload, "Europe/Paris")
    assert "fiction" not in str(caught.value)
    assert "12500" not in str(caught.value)


def test_empty_trip_list_is_valid():
    assert parse_trips({"trips": [], "hasNextPage": False}, "Europe/Paris") == []


def test_nullable_metrics():
    trip, = parse_trips(
        {"trips": [_trip(
            "2026-06-01T10:00:00", score=None, distance=None, stop_time=None, poi_dil=None,
        )]},
        "Europe/Paris",
    )
    assert trip.score is None
    assert trip.distance_km is None
    assert trip.ended_at is None
    assert trip.events == []


def test_policy_ids_are_collected_once_from_nested_objects():
    payload = {"entities": [
        {"EncryptedPolicyGeneralId": " policy-a "},
        {"nested": [
            {"EncryptedPolicyGeneralId": "policy-a"},
            {"EncryptedPolicyGeneralId": "policy-b"},
        ]},
    ]}
    assert policy_ids(payload) == ["policy-a", "policy-b"]
    assert policy_ids({"EncryptedPolicyGeneralId": ""}) == []


def test_authorize_url_uses_proven_pkce_parameters():
    verifier, challenge = pkce_pair()
    url = build_authorize_url("public-client", challenge)
    assert url.startswith(f"{AUTH_ORIGIN}/connect/authorize?")
    assert "response_type=code" in url
    assert "code_challenge_method=S256" in url
    assert "redirect_uri=fr.axa.youdrive%3A%2F%2Fauth" in url
    assert "scope=openid+offline_access+IdentityServerApi+user_context" in url
    assert "idclient" not in url
    assert "00000" not in url
    assert verifier not in url
    assert "=" not in challenge


def test_callback_rejects_a_foreign_url(tmp_path):
    with pytest.raises(AndroidError):
        accept_callback("https://evil.example/?code=fiction", tmp_path)
    assert not (tmp_path / "android-login-callback.txt").exists()
    accept_callback("fr.axa.youdrive://auth?code=fiction-code", tmp_path)
    saved = (tmp_path / "android-login-callback.txt").read_text(encoding="utf-8")
    assert _authorization_code(saved) == "fiction-code"
    slash = "fr.axa.youdrive://auth/?code=fiction-code&scope=openid"
    accept_callback(slash, tmp_path)
    assert _authorization_code(
        (tmp_path / "android-login-callback.txt").read_text(encoding="utf-8"),
    ) == "fiction-code"


def test_redirects_are_refused():
    with pytest.raises(AndroidError, match="Redirection"):
        _RejectRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/")


def test_client_id_comes_from_the_private_apk_asset(tmp_path, monkeypatch):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr(_ENV_NAME, 'OTHER=1\nLOGIN_SSO_WEB_VIEW_CLIENT_ID="public-client"\n')
    monkeypatch.setattr("youdrive.api.android.APK_PATH", apk)
    assert _client_id() == "public-client"


def test_synchronize_reads_every_policy_without_paging(tmp_path):
    settings = _settings(tmp_path)
    _save_session(settings)
    seen = []

    def transport(method, url, headers, data):
        seen.append((method, url, data))
        assert headers["X-AppKey"] == "youdrive_france"
        assert headers["X-Axa-TargetServer"] == "prod"
        assert headers["Authorization"] == "Bearer access-fiction"
        if "motorpartner" in url:
            assert method == "POST"
            assert data == b"{}"
            assert headers["Content-Type"] == "application/json"
            return 200, json.dumps({"entities": [
                {"EncryptedPolicyGeneralId": "policy-a"},
                {"EncryptedPolicyGeneralId": "policy-b"},
            ]}).encode()
        assert method == "GET"
        assert "page=" not in url
        start = "2026-06-01T10:00:00" if "policy-a" in url else "2026-06-02T10:00:00"
        return 200, json.dumps({"trips": [_trip(start)]}).encode()

    batch = synchronize(settings, transport=transport, client_id="public-client")
    assert batch.policy_count == 2
    assert [trip.remote_id for trip in batch.trips] == [
        "android:2026-06-01T10:00:00", "android:2026-06-02T10:00:00",
    ]
    assert not any(item[0] == "POST" and item[1].endswith("/connect/token") for item in seen)


def test_expired_session_is_refreshed_before_reading(tmp_path):
    settings = _settings(tmp_path)
    _save_session(settings, when="2000-01-01T00:00:00+00:00")

    def transport(method, url, headers, data):
        if url.endswith("/connect/token"):
            assert method == "POST"
            assert b"grant_type=refresh_token" in data
            assert b"refresh-fiction" in data
            body = {"access_token": "access-new", "refresh_token": "refresh-new",
                    "expires_in": 3600, "token_type": "Bearer"}
            return 200, json.dumps(body).encode()
        if "motorpartner" in url:
            assert headers["Authorization"] == "Bearer access-new"
            return 200, json.dumps({"EncryptedPolicyGeneralId": "policy-fiction"}).encode()
        return 200, json.dumps({"trips": []}).encode()

    batch = synchronize(settings, transport=transport, client_id="public-client")
    assert batch.trips == []
    saved = json.loads((tmp_path / "android-session.json").read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "refresh-new"


def test_rejected_session_logs_in_once_without_registry(tmp_path):
    settings = _settings(tmp_path)
    _save_session(settings)
    calls = {"motor": 0}

    def transport(method, url, headers, data):
        if url.endswith("/connect/token"):
            assert b"grant_type=authorization_code" in data
            assert b"code=fiction-code" in data
            body = {"access_token": "access-new", "refresh_token": "refresh-new",
                    "expires_in": 3600, "token_type": "Bearer"}
            return 200, json.dumps(body).encode()
        if "motorpartner" in url:
            calls["motor"] += 1
            if calls["motor"] == 1:
                return 401, b"{}"
            return 200, json.dumps({"EncryptedPolicyGeneralId": "policy-fiction"}).encode()
        return 200, json.dumps({"trips": [_trip("2026-06-03T10:00:00")]}).encode()

    def browser(_url):
        accept_callback("fr.axa.youdrive://auth?code=fiction-code", settings.db_path.parent)

    batch = synchronize(
        settings, transport=transport, client_id="public-client", open_browser=browser,
        register=lambda _path: None, sleeper=lambda _seconds: None,
    )
    assert calls["motor"] == 2
    assert len(batch.trips) == 1
    assert not (settings.db_path.parent / "android-login-callback.txt").exists()


def test_json_error_message_is_shown_without_an_address(tmp_path):
    settings = _settings(tmp_path)
    _save_session(settings)

    def transport(method, url, headers, data):
        return 403, b'{"message":"permission required for user@example.com"}'

    with pytest.raises(AndroidError) as caught:
        synchronize(settings, transport=transport, client_id="public-client")
    assert "statut 403" in str(caught.value)
    assert "example.com" not in str(caught.value)


def test_duplicate_identity_across_policies_rejects_before_a_partial_result(tmp_path):
    settings = _settings(tmp_path)
    _save_session(settings)

    def transport(method, url, headers, data):
        if "motorpartner" in url:
            return 200, json.dumps({"entities": [
                {"EncryptedPolicyGeneralId": "policy-a"},
                {"EncryptedPolicyGeneralId": "policy-b"},
            ]}).encode()
        return 200, json.dumps({"trips": [_trip("2026-06-01T10:00:00")]}).encode()

    with pytest.raises(AndroidError, match="dupliqu"):
        synchronize(settings, transport=transport, client_id="public-client")


def test_import_updates_details_and_keeps_claim_and_web_rows(session):
    incoming = parse_trips(
        {"trips": [_trip("2026-06-01T10:00:00", distance=12500)]}, "Europe/Paris",
    )
    assert import_android_trips(session, incoming) == (1, 0)
    session.commit()
    trip = session.scalar(select(Trip).where(Trip.youdrive_id == incoming[0].remote_id))
    imported_at = trip.imported_at
    session.add(Claim(trip_id=trip.id, status=ClaimStatus.PENDING))
    session.add(Trip(
        youdrive_id="web-visible:fiction", started_at=datetime(2026, 1, 1, tzinfo=UTC),
    ))
    session.commit()
    replacement = AndroidTrip(
        incoming[0].remote_id, incoming[0].started_at, incoming[0].ended_at, 100, 12500, 1800,
        [{"kind": "updated"}], {"start": {"address": "fiction"}},
    )
    assert import_android_trips(session, [replacement]) == (0, 1)
    session.commit()
    session.expire_all()
    assert len(list(session.scalars(select(Trip)))) == 2
    assert trip.imported_at == imported_at
    assert trip.score == 100
    assert trip.distance_km == 12500
    assert trip.events == [{"kind": "updated"}]
    assert trip.claim.status == ClaimStatus.PENDING
