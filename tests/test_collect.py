import pytest

from tests.test_screen import card, hierarchy, node
from youdrive.phone.collect import collect_trips
from youdrive.phone.errors import PhoneError


class FakeAdb:
    def __init__(self, dumps: list[str]) -> None:
        self.dumps = list(dumps)
        self.taps: list[tuple[int, int]] = []
        self.swipes = 0
        self.backs = 0
        self.shots: list[str] = []

    def ensure_device(self) -> None:
        return None

    def launch(self) -> None:
        return None

    def dump(self) -> str:
        return self.dumps.pop(0)

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.swipes += 1

    def back(self) -> None:
        self.backs += 1

    def screenshot(self, path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.shots.append(path.name)


def test_scroll_stops_when_the_same_screen_repeats():
    screen = hierarchy(
        node(card(), bounds="[36,400][972,780]"),
        node(card(start="12:00", end="12:20", start_label="Quai Saint-Antoine, 69002 Lyon"),
             bounds="[36,800][972,1180]"),
    )
    adb = FakeAdb([screen, screen])
    trips = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert len(trips) == 2
    assert trips[0].started_at < trips[1].started_at
    assert adb.swipes == 1
    assert adb.taps == []


def test_navigation_opens_recap_then_trips():
    recap = hierarchy(node("RÉCAP\nOnglet 2 sur 5", bounds="[202,1970][403,2136]"))
    tab = hierarchy(node("TRAJETS\nOnglet 2 sur 3", bounds="[348,347][660,419]"))
    screen = hierarchy(node(card()))
    adb = FakeAdb([recap, tab, screen, screen])
    trips = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert len(trips) == 1
    assert adb.taps == [(302, 2053), (504, 383)]


def test_unreadable_card_aborts_before_a_result():
    bad = hierarchy(node("30 sept. 2026\n72\n8 km\n00:23\n19:02"))
    adb = FakeAdb([bad])
    with pytest.raises(PhoneError, match="non reconnue"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None)


def test_missing_tab_aborts():
    adb = FakeAdb([hierarchy(node("ACCUEIL\nOnglet 1 sur 5"))])
    with pytest.raises(PhoneError, match="introuvable"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None)


def test_low_score_detail_is_captured_and_perfect_score_is_not(tmp_path):
    listed = hierarchy(
        node(card(score="72"), bounds="[36,437][972,919]"),
        node(
            card(
                score="100", start="12:00", end="12:20",
                start_label="Quai Saint-Antoine, 69002 Lyon",
            ),
            bounds="[36,960][972,1440]",
        ),
    )
    detail = hierarchy(node("VITESSE", clickable="false", bounds="[40,700][300,780]"))
    adb = FakeAdb([listed, detail, listed, listed])
    trips = collect_trips(adb, "Europe/Paris", lambda _delay: None, tmp_path)
    low = next(trip for trip in trips if trip.score == 72)
    perfect = next(trip for trip in trips if trip.score == 100)
    assert low.screenshot_name is not None
    assert (tmp_path / low.screenshot_name).is_file()
    assert perfect.screenshot_name is None
    assert adb.shots == [low.screenshot_name]
    assert adb.backs == 1
    assert len(adb.taps) == 1


def test_untappable_low_score_does_not_import(tmp_path):
    listed = hierarchy(node(card(score="72"), bounds="[36,1800][972,1830]"))
    adb = FakeAdb([listed, listed])
    with pytest.raises(PhoneError, match="Capture du détail"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None, tmp_path)
    assert adb.shots == []


def test_unstable_list_is_not_returned(monkeypatch):
    monkeypatch.setattr("youdrive.phone.collect.MAX_SCROLLS", 2)
    dumps = [
        hierarchy(node(card(start=f"{10 + index}:00", end=f"{10 + index}:20")))
        for index in range(3)
    ]
    adb = FakeAdb(dumps)
    with pytest.raises(PhoneError, match="incomplète"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None)
