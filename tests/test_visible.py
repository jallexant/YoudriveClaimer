from datetime import UTC, datetime

import pytest

from youdrive.api.visible import parse_visible
from youdrive.api.web import WebError


def visible_payload(page="history", **changes):
    row = {
        "date": "27 septembre 2026", "start": "11:11", "end": "11:22",
        "score": "100", "distance": "8,2 km", "duration": "00:11", "identity": "a" * 64,
    }
    row.update(changes)
    return {"source": "direct-assurance-visible-v1", "page": page, "trips": [row]}


def test_visible_values_use_paris_timezone_and_provisional_identity():
    trip = parse_visible(visible_payload())[0]
    assert trip.remote_id == "web-visible:" + "a" * 64
    assert trip.started_at == datetime(2026, 9, 27, 9, 11, tzinfo=UTC)
    assert trip.ended_at == datetime(2026, 9, 27, 9, 22, tzinfo=UTC)
    assert trip.score == 100
    assert trip.distance_km == 8.2
    assert trip.duration_seconds == 660


def test_visible_midnight_rollover_crosses_calendar_year():
    trip = parse_visible(visible_payload(
        date="31 décembre 2026", start="23:58", end="00:10", duration="00:12",
    ))[0]
    assert trip.started_at == datetime(2026, 12, 31, 22, 58, tzinfo=UTC)
    assert trip.ended_at == datetime(2026, 12, 31, 23, 10, tzinfo=UTC)
    assert trip.duration_seconds == 720


def test_visible_normal_spring_clock_transition_has_correct_utc_instants():
    trip = parse_visible(visible_payload(
        date="29 mars 2026", start="01:50", end="03:10", duration="00:20",
    ))[0]
    assert trip.started_at == datetime(2026, 3, 29, 0, 50, tzinfo=UTC)
    assert trip.ended_at == datetime(2026, 3, 29, 1, 10, tzinfo=UTC)


@pytest.mark.parametrize("day", ["29 mars 2026", "25 octobre 2026"])
@pytest.mark.parametrize("field", ["start", "end"])
def test_visible_refuses_nonexistent_and_ambiguous_paris_times(day, field):
    changes = {"date": day, "start": "01:10", "end": "03:10", field: "02:30"}
    with pytest.raises(WebError, match="ambiguë ou inexistante"):
        parse_visible(visible_payload(**changes))


@pytest.mark.parametrize("score", ["", "  ", None])
def test_empty_score_is_unknown(score):
    assert parse_visible(visible_payload(score=score))[0].score is None


def test_score_change_does_not_change_provisional_identity():
    first = parse_visible(visible_payload(score="72"))[0]
    corrected = parse_visible(visible_payload(score="100"))[0]
    assert first.remote_id == corrected.remote_id
    assert first.score == 72
    assert corrected.score == 100


def test_visible_rejects_identity_collision_in_whole_batch():
    payload = visible_payload()
    payload["trips"].append(dict(payload["trips"][0], score="85", identity="A" * 64))
    with pytest.raises(WebError, match="dupliquée"):
        parse_visible(payload)


@pytest.mark.parametrize("page,maximum", [("history", 10), ("dashboard", 3)])
def test_visible_page_specific_limits(page, maximum):
    payload = visible_payload(page=page)
    row = payload["trips"][0]
    payload["trips"] = [dict(row, identity=f"{index:064x}") for index in range(maximum)]
    assert len(parse_visible(payload)) == maximum
    payload["trips"].append(dict(row, identity=f"{maximum:064x}"))
    with pytest.raises(WebError, match="Nombre"):
        parse_visible(payload)


@pytest.mark.parametrize("changes", [
    {"date": "31 février 2026"}, {"date": "27/09/2026"}, {"date": "27 september 2026"},
    {"date": "1 janvier 0001", "start": "00:00"},
    {"date": "31 décembre 9999", "start": "23:59", "end": "00:00"},
    {"start": "24:00"}, {"start": "1:00"}, {"end": "12:60"},
    {"score": "101"}, {"score": "-1"}, {"score": "nan"}, {"score": float("inf")},
    {"score": True}, {"distance": "8,2 mi"}, {"distance": "-8 km"},
    {"distance": "Infinity km"}, {"duration": "00:60"}, {"duration": "-1:00"},
    {"identity": "a" * 63}, {"identity": "z" * 64}, {"identity": None},
])
def test_invalid_visible_values_refuse_import(changes):
    with pytest.raises(WebError):
        parse_visible(visible_payload(**changes))


@pytest.mark.parametrize("payload", [
    None, [], {}, {"source": "wrong", "page": "history", "trips": []},
    {"source": "direct-assurance-visible-v1", "page": "unknown", "trips": []},
    {"source": "direct-assurance-visible-v1", "page": "history", "trips": {}},
])
def test_unrecognized_visible_envelope_refused(payload):
    with pytest.raises(WebError):
        parse_visible(payload)


def test_malformed_second_row_refuses_whole_batch_without_echoing_data():
    payload = visible_payload()
    payload["trips"].append(dict(payload["trips"][0], identity="b" * 64,
                                 date="fake-sensitive-address"))
    with pytest.raises(WebError) as caught:
        parse_visible(payload)
    assert "fake-sensitive-address" not in str(caught.value)


def test_longer_duration_and_nonbreaking_space_distance():
    trip = parse_visible(visible_payload(duration="2:05", distance="1234,5\u00a0km"))[0]
    assert trip.duration_seconds == 7500
    assert trip.distance_km == 1234.5
