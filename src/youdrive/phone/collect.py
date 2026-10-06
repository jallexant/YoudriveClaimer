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
LAUNCH_ATTEMPTS = 3
POLLS_PER_LAUNCH = 16


def collect_trips(
    adb: Adb, timezone: str, sleeper: Callable[[float], None],
    screenshot_dir: Path | None = None, known_ids: set[str] | None = None,
) -> tuple[list[PhoneTrip], bool]:
    adb.ensure_device()
    xml = _await_youdrive(adb, timezone, sleeper)
    xml = _open_trips(adb, xml, timezone, sleeper)
    adb.rewind()
    sleeper(0.8)
    xml = adb.dump()
    seen: dict[str, PhoneTrip] = {}
    captured: set[str] = set()
    known = known_ids or set()
    previous: tuple[str, ...] | None = None
    stagnant = 0
    for _ in range(MAX_SCROLLS):
        cards = parse_cards(xml, timezone)
        fresh: list[PhoneTrip] = []
        reached_known = False
        for card in cards:
            if card.remote_id in known:
                reached_known = True
                break
            fresh.append(card)
        if screenshot_dir is not None:
            xml = _shoot_visible(
                adb, xml, timezone, screenshot_dir, captured, sleeper,
                {card.remote_id for card in fresh},
            )
        for card in fresh:
            seen[card.remote_id] = card
        if reached_known:
            return _finish(seen, captured, screenshot_dir), True
        current = tuple(card.remote_id for card in cards)
        stagnant = stagnant + 1 if previous == current else 0
        if stagnant >= 2:
            return _finish(seen, captured, screenshot_dir), False
        previous = current
        xml = _scroll_with_overlap(adb, xml, set(current), timezone, sleeper)
    raise PhoneError("Liste incomplète ; aucun import effectué.")


def _scroll_with_overlap(
    adb: Adb, xml: str, before: set[str], timezone: str, sleeper: Callable[[float], None],
) -> str:
    x1, y1, x2, y2 = swipe_points(xml)
    adb.swipe(x1, y1, x2, y2)
    sleeper(0.8)
    xml = adb.dump()
    for _ in range(4):
        after = {card.remote_id for card in parse_cards(xml, timezone)}
        if not before or not after or before & after:
            return xml
        adb.swipe(x1, y2, x1, y2 + (y1 - y2) // 2)
        sleeper(0.8)
        xml = adb.dump()
    raise PhoneError("Défilement trop rapide ; aucun import effectué.")


def _finish(
    seen: dict[str, PhoneTrip], captured: set[str], screenshot_dir: Path | None,
) -> list[PhoneTrip]:
    trips = sorted(seen.values(), key=lambda trip: (trip.started_at, trip.remote_id))
    if screenshot_dir is not None and any(
        trip.score < 100 and trip.remote_id not in captured for trip in trips
    ):
        raise PhoneError("Capture du détail incomplète ; aucun import effectué.")
    return [with_screenshot(trip) if trip.remote_id in captured else trip for trip in trips]


def _shoot_visible(
    adb: Adb, xml: str, timezone: str, directory: Path, captured: set[str],
    sleeper: Callable[[float], None], allowed: set[str],
) -> str:
    for _ in range(8):
        targets = [
            (trip, bounds)
            for trip, bounds in parse_visible_cards(xml, timezone)
            if trip.remote_id in allowed and trip.score < 100
            and trip.remote_id not in captured and tappable(bounds)
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


def _await_youdrive(
    adb: Adb, timezone: str, sleeper: Callable[[float], None],
) -> str:
    for _attempt in range(LAUNCH_ATTEMPTS):
        adb.launch()
        sleeper(2.0)
        seen_running = False
        for _poll in range(POLLS_PER_LAUNCH):
            running = adb.app_running()
            if running:
                seen_running = True
                xml = adb.try_dump()
                if xml is not None and _screen_ready(xml, timezone):
                    return xml
            elif seen_running:
                break
            sleeper(1.5)
    raise PhoneError(
        "Onglet Trajets introuvable ; l'application s'est fermée "
        "ou n'a pas fini de s'afficher. Aucun import effectué.",
    )


def _screen_ready(xml: str, timezone: str) -> bool:
    if has_label(xml, "RÉCAP") or has_label(xml, "TRAJETS"):
        return True
    return bool(parse_cards(xml, timezone))


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
