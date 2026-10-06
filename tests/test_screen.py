import pytest

from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import find_label, parse_cards, swipe_points


def hierarchy(*nodes: str) -> str:
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def node(desc: str, *, clickable: str = "true", bounds: str = "[36,400][972,780]") -> str:
    escaped = desc.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    escaped = escaped.replace("\n", "&#10;")
    return (
        f'<node package="fr.axa.youdrive" clickable="{clickable}" '
        f'bounds="{bounds}" content-desc="{escaped}"/>'
    )


def card(**overrides: str) -> str:
    lines = {
        "date": "30 sept. 2026",
        "score": "72",
        "distance": "8 km",
        "duration": "00:23",
        "start": "19:02",
        "start_label": "Rue de la Paix, 75002 Paris",
        "end": "19:26",
        "end_label": "Avenue Victor Hugo, 75016 Paris",
    }
    lines.update(overrides)
    return "\n".join(lines[key] for key in (
        "date", "score", "distance", "duration", "start", "start_label", "end", "end_label",
    ))


def test_card_reads_score_distance_and_keeps_identity_when_score_changes():
    first = parse_cards(hierarchy(node(card())), "Europe/Paris")[0]
    second = parse_cards(hierarchy(node(card(score="80"))), "Europe/Paris")[0]
    assert first.remote_id == second.remote_id
    assert first.remote_id.startswith("phone:")
    assert first.score == 72
    assert first.distance_km == 8
    assert first.duration_seconds == 23 * 60
    assert first.started_at.isoformat() == "2026-09-30T17:02:00+00:00"
    assert first.ended_at.isoformat() == "2026-09-30T17:26:00+00:00"
    assert first.start_label == "Rue de la Paix, 75002 Paris"


def test_address_change_is_another_trip():
    first = parse_cards(hierarchy(node(card())), "Europe/Paris")[0]
    second = parse_cards(
        hierarchy(node(card(end_label="Place Bellecour, 69002 Lyon"))), "Europe/Paris",
    )[0]
    assert first.remote_id != second.remote_id


def test_overnight_trip_ends_the_next_day():
    trip = parse_cards(
        hierarchy(node(card(start="23:50", end="00:10", duration="00:20"))), "Europe/Paris",
    )[0]
    assert trip.ended_at.isoformat() == "2026-09-30T22:10:00+00:00"
    assert trip.started_at.isoformat() == "2026-09-30T21:50:00+00:00"


def test_tabs_and_non_clickable_dates_are_ignored():
    xml = hierarchy(
        node("TRAJETS\nOnglet 2 sur 3", bounds="[348,347][660,419]"),
        node(card(), clickable="false"),
    )
    assert parse_cards(xml, "Europe/Paris") == []
    assert find_label(xml, "TRAJETS") == "[348,347][660,419]"
    assert find_label(xml, "RÉCAP") is None


def test_unreadable_card_rejects_the_screen():
    with pytest.raises(PhoneError, match="non reconnue"):
        parse_cards(hierarchy(node("30 sept. 2026\n72\n8 km")), "Europe/Paris")


def test_unrecorded_trip_without_score_is_ignored():
    unavailable = "\n".join([
        "22 sept. 2026",
        "27 km",
        "00:27",
        "12:21 - 12:48",
        "Trajet non enregistré. Votre téléphone doit être connecté pour bénéficier "
        "de votre remise sur chaque trajet.",
    ])
    xml = hierarchy(node(unavailable), node(card(date="22 sept. 2026")))
    trips = parse_cards(xml, "Europe/Paris")
    assert len(trips) == 1
    assert trips[0].score == 72


def test_ambiguous_and_missing_hours_are_rejected():
    ambiguous = card(date="25 oct. 2026", start="02:30", end="03:00")
    missing = card(date="29 mars 2026", start="02:30", end="03:10")
    for desc in (ambiguous, missing):
        with pytest.raises(PhoneError, match="ambiguë ou inexistante"):
            parse_cards(hierarchy(node(desc)), "Europe/Paris")


def test_dump_prefix_is_ignored_and_duplicate_card_is_rejected():
    prefixed = "UI hierchary dumped to: /sdcard/window_dump.xml\n" + hierarchy(node(card()))
    assert len(parse_cards(prefixed, "Europe/Paris")) == 1
    with pytest.raises(PhoneError, match="dupliquée"):
        duplicated = hierarchy(node(card()), node(card(), bounds="[36,800][972,1180]"))
        parse_cards(duplicated, "Europe/Paris")


def test_swipe_uses_the_card_column():
    assert swipe_points(hierarchy(node(card())))[0] == 504
