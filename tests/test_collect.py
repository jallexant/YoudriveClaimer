import pytest

from tests.test_screen import card, hierarchy, node
from youdrive.phone.collect import collect_trips
from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import parse_cards


class FakeAdb:
    def __init__(self, dumps: list[str], running: list[bool] | None = None) -> None:
        self.dumps = list(dumps)
        self.taps: list[tuple[int, int]] = []
        self.swipes = 0
        self.backs = 0
        self.shots: list[str] = []
        self.rewinds = 0
        self.launches = 0
        self.running = list(running) if running is not None else []

    def ensure_device(self) -> None:
        return None

    def launch(self) -> None:
        self.launches += 1

    def app_running(self) -> bool:
        if not self.running:
            return True
        return self.running.pop(0)

    def try_dump(self) -> str | None:
        return self.dump()

    def dump(self) -> str:
        return self.dumps.pop(0)

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.swipes += 1

    def back(self) -> None:
        self.backs += 1

    def rewind(self) -> None:
        self.rewinds += 1

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
    adb = FakeAdb([screen, screen, screen, screen])
    trips, reached = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert reached is False
    assert len(trips) == 2
    assert trips[0].started_at < trips[1].started_at
    assert adb.swipes == 2
    assert adb.taps == []
    assert adb.rewinds == 1


def test_navigation_opens_recap_then_trips():
    recap = hierarchy(node("RÉCAP\nOnglet 2 sur 5", bounds="[202,1970][403,2136]"))
    tab = hierarchy(node("TRAJETS\nOnglet 2 sur 3", bounds="[348,347][660,419]"))
    screen = hierarchy(node(card()))
    adb = FakeAdb([recap, tab, screen, screen, screen, screen])
    trips, reached = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert reached is False
    assert len(trips) == 1
    assert adb.taps == [(302, 2053), (504, 383)]


def test_collection_stops_at_the_first_known_trip_without_scrolling_further():
    screen = hierarchy(
        node(card(), bounds="[36,400][972,780]"),
        node(card(start="12:00", end="12:20", start_label="Quai Saint-Antoine, 69002 Lyon"),
             bounds="[36,800][972,1180]"),
    )
    known = parse_cards(screen, "Europe/Paris")[1].remote_id
    adb = FakeAdb([screen, screen])
    trips, reached = collect_trips(
        adb, "Europe/Paris", lambda _delay: None, known_ids={known},
    )
    assert reached is True
    assert len(trips) == 1
    assert trips[0].remote_id != known
    assert adb.swipes == 0


def test_scroll_that_jumps_past_cards_is_corrected():
    def trip(hour: int) -> str:
        return node(card(start=f"{hour}:00", end=f"{hour}:20"))

    first = hierarchy(trip(18), trip(17))
    jumped = hierarchy(trip(14))
    back = hierarchy(trip(17), trip(16))
    last = hierarchy(trip(16), trip(15), trip(14))
    adb = FakeAdb([first, first, jumped, back, last, last, last])
    trips, reached = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert reached is False
    assert [t.started_at.hour for t in trips] == [12, 13, 14, 15, 16]
    assert adb.swipes == 5


def test_unreadable_card_aborts_before_a_result():
    bad = hierarchy(node("30 sept. 2026\n72\n8 km\n00:23\n19:02"))
    adb = FakeAdb([bad])
    with pytest.raises(PhoneError, match="non reconnue"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None)


def test_missing_tab_aborts(monkeypatch):
    monkeypatch.setattr("youdrive.phone.collect.LAUNCH_ATTEMPTS", 1)
    monkeypatch.setattr("youdrive.phone.collect.POLLS_PER_LAUNCH", 1)
    adb = FakeAdb([hierarchy(node("ACCUEIL\nOnglet 1 sur 5"))])
    with pytest.raises(PhoneError, match="introuvable"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None)


def test_slow_launch_waits_until_the_tabs_appear():
    splash = hierarchy(node("Chargement"))
    recap = hierarchy(node("RÉCAP\nOnglet 2 sur 5", bounds="[202,1970][403,2136]"))
    tab = hierarchy(node("TRAJETS\nOnglet 2 sur 3", bounds="[348,347][660,419]"))
    screen = hierarchy(node(card()))
    adb = FakeAdb([splash, recap, tab, screen, screen, screen, screen])
    trips, reached = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert reached is False
    assert len(trips) == 1
    assert adb.launches == 1


def test_closed_app_is_launched_again():
    splash = hierarchy(node("Chargement"))
    screen = hierarchy(node(card()))
    adb = FakeAdb(
        [splash, screen, screen, screen, screen],
        running=[True, False, True],
    )
    trips, reached = collect_trips(adb, "Europe/Paris", lambda _delay: None)
    assert reached is False
    assert len(trips) == 1
    assert adb.launches == 2


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
    adb = FakeAdb([listed, listed, detail, listed, listed, listed])
    trips, reached = collect_trips(adb, "Europe/Paris", lambda _delay: None, tmp_path)
    assert reached is False
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
    adb = FakeAdb([listed, listed, listed, listed])
    with pytest.raises(PhoneError, match="Capture du détail"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None, tmp_path)
    assert adb.shots == []


def test_slow_open_says_the_screen_is_still_loading():
    screen = hierarchy(node(card(), bounds="[36,400][972,780]"))
    adb = FakeAdb([screen, screen, screen, screen], [False, False, False, False, True])
    notes = []
    trips, reached = collect_trips(
        adb, "Europe/Paris", lambda _delay: None, on_progress=notes.append,
    )
    assert reached is False
    assert trips
    assert "L'écran YouDrive se charge." in notes
    assert "Rue de la Paix" not in "\n".join(notes)


def test_progress_counts_trips_without_copying_addresses():
    screen = hierarchy(node(card(), bounds="[36,400][972,780]"))
    adb = FakeAdb([screen, screen, screen, screen])
    notes = []
    trips, reached = collect_trips(
        adb, "Europe/Paris", lambda _delay: None, on_progress=notes.append,
    )
    assert reached is False
    assert trips
    text = "\n".join(notes)
    assert "Trajets lus : 1." in text
    assert "Retour en haut de la liste." in text
    assert "Fin de la liste." in text
    assert "Rue de la Paix" not in text
    assert "Victor Hugo" not in text


def test_unstable_list_is_not_returned(monkeypatch):
    monkeypatch.setattr("youdrive.phone.collect.MAX_SCROLLS", 2)

    def trip(hour: int) -> str:
        return node(card(start=f"{hour:02d}:00", end=f"{hour:02d}:20"))

    dumps = [hierarchy(trip(9), trip(10))] + [
        hierarchy(trip(9 + index), trip(10 + index)) for index in range(3)
    ]
    adb = FakeAdb(dumps)
    with pytest.raises(PhoneError, match="incomplète"):
        collect_trips(adb, "Europe/Paris", lambda _delay: None)
