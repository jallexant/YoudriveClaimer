"""Open the trip list and scroll until the same cards repeat."""

from collections.abc import Callable

from youdrive.phone.adb import Adb
from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import (
    PhoneTrip,
    center,
    find_label,
    has_label,
    parse_cards,
    swipe_points,
)

MAX_SCROLLS = 200


def collect_trips(
    adb: Adb, timezone: str, sleeper: Callable[[float], None],
) -> list[PhoneTrip]:
    adb.ensure_device()
    adb.launch()
    sleeper(1.2)
    xml = _open_trips(adb, adb.dump(), timezone, sleeper)
    seen: dict[str, PhoneTrip] = {}
    previous: tuple[str, ...] | None = None
    for _ in range(MAX_SCROLLS):
        cards = parse_cards(xml, timezone)
        current = tuple(card.remote_id for card in cards)
        if previous == current:
            return sorted(seen.values(), key=lambda trip: (trip.started_at, trip.remote_id))
        for card in cards:
            seen[card.remote_id] = card
        previous = current
        x1, y1, x2, y2 = swipe_points(xml)
        adb.swipe(x1, y1, x2, y2)
        sleeper(0.8)
        xml = adb.dump()
    raise PhoneError("Liste incomplète ; aucun import effectué.")


def _open_trips(
    adb: Adb, xml: str, timezone: str, sleeper: Callable[[float], None],
) -> str:
    if parse_cards(xml, timezone):
        return xml
    if not has_label(xml, "TRAJETS"):
        recap = find_label(xml, "RÉCAP")
        if recap is None:
            raise PhoneError("Onglet Trajets introuvable ; aucun import effectué.")
        adb.tap(*center(recap))
        sleeper(0.8)
        xml = adb.dump()
    if parse_cards(xml, timezone):
        return xml
    trips = find_label(xml, "TRAJETS")
    if trips is None:
        raise PhoneError("Onglet Trajets introuvable ; aucun import effectué.")
    adb.tap(*center(trips))
    sleeper(0.8)
    xml = adb.dump()
    if not parse_cards(xml, timezone) and not has_label(xml, "TRAJETS"):
        raise PhoneError("Onglet Trajets introuvable ; aucun import effectué.")
    return xml
