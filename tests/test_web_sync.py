from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from youdrive.api.web import (
    ORIGIN,
    WebError,
    _load_session,
    _save_session,
    parse_trips,
    validate_trip_url,
)
from youdrive.models import Claim, ClaimStatus, Trip
from youdrive.services.sync import import_web_trips

URL = f"{ORIGIN}/api/private-domain-redesign/youdrive/policy/fake-policy/trips?numberOfTrips=13"


def payload():
    return {"status": 0, "data": [{
        "id": "fake-trip", "startDate": "2026-09-01T14:00:00+02:00",
        "endDate": "2026-09-01T14:30:00+02:00", "score": 85,
        "distance": 12.5, "durationInMinutes": 30,
    }]}


def test_parse_observed_fields_with_timezone():
    trip, = parse_trips(payload(), validate_trip_url(URL))
    assert trip.started_at == datetime(2026, 9, 1, 12, tzinfo=UTC)
    assert trip.duration_seconds == 1800
    assert trip.distance_km == 12.5
    assert trip.score == 85


@pytest.mark.parametrize("change", [
    {"startDate": "2026-09-01T14:00:00"}, {"score": True}, {"score": "85"},
    {"score": 101}, {"distance": float("nan")}, {"id": None},
    {"endDate": "2026-08-01T14:00:00Z"}, {"durationInMinutes": -1},
])
def test_schema_changes_are_rejected_without_echoing_payload(change):
    data = payload()
    data["data"][0].update(change)
    with pytest.raises(WebError) as caught:
        parse_trips(data, "fake-scope")
    assert "fake-trip" not in str(caught.value)


def test_nullable_metrics_stay_unknown_and_duplicate_ids_are_rejected():
    data = payload()
    data["data"][0].update(score=None, distance=None, durationInMinutes=None)
    trip, = parse_trips(data, "fake-scope")
    assert trip.score is None
    data["data"].append(data["data"][0].copy())
    with pytest.raises(WebError):
        parse_trips(data, "fake-scope")


def test_unauthorized_and_unrecognized_envelopes_are_rejected():
    for data in [{"status": 3}, {"status": True, "data": []}, {"status": 0, "data": {}},
                 {"status": 2, "data": []}, {}]:
        with pytest.raises(WebError):
            parse_trips(data, "fake-scope")
    assert parse_trips({"status": 0, "data": []}, "fake-scope") == []


@pytest.mark.parametrize("url", [
    URL.replace("https:", "http:"), URL.replace("espace-personnel", "evil"),
    URL.replace("13", "100"), URL + "&extra=1", URL + "#fragment",
    URL.replace("/trips?", "/delete?"),
    URL.replace("direct-assurance.fr/", "direct-assurance.fr:443/"),
])
def test_only_exact_official_read_endpoint_is_allowed(url):
    with pytest.raises(WebError):
        validate_trip_url(url)


def test_private_session_roundtrip_and_invalid_session(tmp_path):
    file = tmp_path / "session.json"
    _save_session(file, URL, {"cookies": [], "origins": []})
    assert _load_session(file)["trip_url"] == URL
    file.write_text('{"trip_url": "fake-secret"}', encoding="utf-8")
    with pytest.raises(WebError) as caught:
        _load_session(file)
    assert "fake-secret" not in str(caught.value)


def test_sync_is_idempotent_preserves_claim_details_and_absent_old_trips(session):
    incoming = parse_trips(payload(), "fake-scope")
    assert import_web_trips(session, incoming) == (1, 0)
    session.commit()
    trip = session.scalar(select(Trip))
    imported_at = trip.imported_at
    trip.events = [{"type": "fake-event"}]
    trip.gps = {"fake": True}
    session.add(Claim(trip_id=trip.id, status=ClaimStatus.PENDING))
    session.add(Trip(youdrive_id="fake-old", started_at=datetime(2026, 1, 1, tzinfo=UTC)))
    session.commit()
    assert import_web_trips(session, [replace(incoming[0], score=100)]) == (0, 1)
    session.commit()
    session.expire_all()
    assert len(list(session.scalars(select(Trip)))) == 2
    assert trip.imported_at == imported_at
    assert trip.events == [{"type": "fake-event"}]
    assert trip.gps == {"fake": True}
    assert trip.score == 100
    assert trip.claim.status == ClaimStatus.PENDING
    assert import_web_trips(session, []) == (0, 0)
