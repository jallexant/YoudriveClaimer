"""Open the trip list and scroll until the same cards repeat."""

from collections.abc import Callable
from pathlib import Path

from youdrive.phone.adb import Adb
from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import (
    PhoneTrip,
    center,
    find_label,
    has_label,
    parse_cards,
    parse_visible_cards,
    screen_contains,
    screenshot_filename,
    swipe_points,
    tappable,
    with_screenshot,
)

MAX_SCROLLS = 200


def collect_trips(
    adb: Adb, timezone: str, sleeper: Callable[[float], None],
    screenshot_dir: Path | None = None,
) -> list[PhoneTrip]:
    adb.ensure_device()
    adb.launch()
    sleeper(1.2)
    xml = _open_trips(adb, adb.dump(), timezone, sleeper)
    seen: dict[str, PhoneTrip] = {}
    captured: set[str] = set()
    previous: tuple[str, ...] | None = None
    for _ in range(MAX_SCROLLS):
        if screenshot_dir is not None:
            xml = _shoot_visible(adb, xml, timezone, screenshot_dir, captured, sleeper)
        cards = parse_cards(xml, timezone)
        current = tuple(card.remote_id for card in cards)
        if previous == current:
            trips = sorted(seen.values(), key=lambda trip: (trip.started_at, trip.remote_id))
            if screenshot_dir is not None and any(
                trip.score < 100 and trip.remote_id not in captured for trip in trips
            ):
                raise PhoneError("Capture du détail incomplète ; aucun import effectué.")
            return [
                with_screenshot(trip) if trip.remote_id in captured else trip for trip in trips
            ]
        for card in cards:
            seen[card.remote_id] = card
        previous = current
        x1, y1, x2, y2 = swipe_points(xml)
        adb.swipe(x1, y1, x2, y2)
        sleeper(0.8)
        xml = adb.dump()
    raise PhoneError("Liste incomplète ; aucun import effectué.")


def _shoot_visible(
    adb: Adb, xml: str, timezone: str, directory: Path, captured: set[str],
    sleeper: Callable[[float], None],
) -> str:
    for _ in range(8):
        targets = [
            (trip, bounds)
            for trip, bounds in parse_visible_cards(xml, timezone)
            if trip.score < 100 and trip.remote_id not in captured and tappable(bounds)
        ]
        if not targets:
            return xml
        trip, bounds = targets[0]
        adb.tap(*center(bounds))
        detail, seen = _wait_detail(adb, timezone, sleeper)
        if detail is None:
            if not parse_cards(seen, timezone):
                adb.back()
                sleeper(0.8)
                seen = adb.dump()
            xml = seen
            continue
        directory.mkdir(parents=True, exist_ok=True)
        adb.screenshot(directory / screenshot_filename(trip.remote_id))
        captured.add(trip.remote_id)
        adb.back()
        sleeper(0.8)
        xml = _return_to_anchor(adb, adb.dump(), trip.remote_id, timezone, sleeper)
    return xml


def _wait_detail(
    adb: Adb, timezone: str, sleeper: Callable[[float], None],
) -> tuple[str | None, str]:
    xml = ""
    for _ in range(4):
        sleeper(0.6)
        xml = adb.dump()
        if screen_contains(xml, "VITESSE"):
            return xml, xml
        if parse_cards(xml, timezone):
            return None, xml
    return None, xml


def _return_to_anchor(
    adb: Adb, xml: str, anchor: str, timezone: str, sleeper: Callable[[float], None],
) -> str:
    previous: tuple[str, ...] | None = None
    for _ in range(MAX_SCROLLS):
        cards = parse_cards(xml, timezone)
        current = tuple(card.remote_id for card in cards)
        if anchor in current:
            return xml
        if not current:
            xml = _open_trips(adb, xml, timezone, sleeper)
            continue
        if previous == current:
            raise PhoneError("Capture du détail incomplète ; aucun import effectué.")
        previous = current
        x1, y1, _x2, y2 = swipe_points(xml)
        adb.swipe(x1, y1, x1, max(y2, y1 - 450))
        sleeper(0.5)
        xml = adb.dump()
    raise PhoneError("Capture du détail incomplète ; aucun import effectué.")


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
