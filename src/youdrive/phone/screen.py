"""Read trip cards from a YouDrive accessibility dump."""

import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from youdrive.phone.errors import PhoneError

PACKAGE = "fr.axa.youdrive"
_MAX_XML = 5_000_000
_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_DATE = re.compile(r"(\d{1,2}) ([a-zàâéèêëîïôùûüç.]+) (\d{4})", re.IGNORECASE)
_SCORE = re.compile(r"\d{1,3}(?:[,.]\d+)?")
_DISTANCE = re.compile(r"(\d+(?:[,.]\d+)?) km", re.IGNORECASE)
_CLOCK = re.compile(r"(\d{2}):([0-5]\d)")
_DURATION = re.compile(r"(\d{1,6}):([0-5]\d)")
_MONTHS = {
    "janv": 1, "janvier": 1, "févr": 2, "fevr": 2, "février": 2, "fevrier": 2,
    "mars": 3, "avr": 4, "avril": 4, "mai": 5, "juin": 6, "juil": 7, "juillet": 7,
    "août": 8, "aout": 8, "sept": 9, "septembre": 9, "oct": 10, "octobre": 10,
    "nov": 11, "novembre": 11, "déc": 12, "dec": 12, "décembre": 12, "decembre": 12,
}
_PARIS = ZoneInfo("Europe/Paris")


@dataclass(frozen=True)
class PhoneTrip:
    remote_id: str
    started_at: datetime
    ended_at: datetime
    score: float
    distance_km: float
    duration_seconds: int
    start_label: str
    end_label: str


def parse_cards(xml: str, timezone: str) -> list[PhoneTrip]:
    zone = ZoneInfo(timezone)
    cards = []
    for node in _trip_nodes(_root(xml)):
        cards.append(_card(node["desc"], zone))
    identities = [card.remote_id for card in cards]
    if len(identities) != len(set(identities)):
        raise PhoneError("Identité de trajet dupliquée ; aucun import effectué.")
    return cards


def has_label(xml: str, prefix: str) -> bool:
    return find_label(xml, prefix) is not None


def find_label(xml: str, prefix: str) -> str | None:
    folded = _fold(prefix)
    for node in _nodes(_root(xml)):
        if node["package"] != PACKAGE or not node["clickable"]:
            continue
        if _fold(_first_line(node["desc"])).startswith(folded):
            return node["bounds"]
    return None


def center(bounds: str) -> tuple[int, int]:
    match = _BOUNDS.fullmatch(bounds)
    if match is None:
        raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")
    left, top, right, bottom = (int(item) for item in match.groups())
    return (left + right) // 2, (top + bottom) // 2


def swipe_points(xml: str) -> tuple[int, int, int, int]:
    boxes = []
    for node in _trip_nodes(_root(xml)):
        match = _BOUNDS.fullmatch(node["bounds"])
        if match is not None:
            boxes.append(tuple(int(item) for item in match.groups()))
    if not boxes:
        return (500, 1600, 500, 700)
    left, top, right, _bottom = boxes[0]
    lowest = max(box[3] for box in boxes)
    highest = min(box[1] for box in boxes)
    start = lowest - 40
    end = highest + 40
    if start - end < 240:
        start = highest + 900
        end = highest + 200
    return ((left + right) // 2, start, (left + right) // 2, end)


def _card(desc: str, zone: ZoneInfo) -> PhoneTrip:
    lines = [line.strip() for line in desc.splitlines() if line.strip()]
    if len(lines) != 8:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    day = _calendar_date(lines[0])
    score = _score(lines[1])
    distance_text, distance = _distance(lines[2])
    duration = _duration(lines[3])
    start = _clock(lines[4])
    end = _clock(lines[6])
    start_label = _label(lines[5])
    end_label = _label(lines[7])
    started_at = _paris_datetime(day, start, zone)
    end_day = day + timedelta(days=1) if end < start else day
    ended_at = _paris_datetime(end_day, end, zone)
    if ended_at < started_at:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    identity = "\n".join([
        day.isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"),
        distance_text, start_label, end_label,
    ])
    return PhoneTrip(
        remote_id="phone:" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        started_at=started_at, ended_at=ended_at, score=score, distance_km=distance,
        duration_seconds=duration, start_label=start_label, end_label=end_label,
    )


def _root(xml: str):
    if not isinstance(xml, str) or not xml.strip() or len(xml) > _MAX_XML:
        raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")
    start = xml.find("<hierarchy")
    if start < 0:
        start = xml.find("<?xml")
    if start < 0:
        raise PhoneError("Écran YouDrive illisible ; aucun import effectué.")
    try:
        return ET.fromstring(xml[start:])
    except ET.ParseError:
        raise PhoneError("Écran YouDrive illisible ; aucun import effectué.") from None


def _nodes(root) -> list[dict[str, str | bool]]:
    found = []
    for node in root.iter("node"):
        found.append({
            "desc": node.attrib.get("content-desc") or "",
            "clickable": node.attrib.get("clickable") == "true",
            "bounds": node.attrib.get("bounds") or "",
            "package": node.attrib.get("package") or "",
        })
    return found


def _trip_nodes(root) -> list[dict[str, str | bool]]:
    cards = []
    for node in _nodes(root):
        if node["package"] != PACKAGE or not node["clickable"]:
            continue
        if _DATE.fullmatch(_first_line(str(node["desc"]))):
            cards.append(node)
    return cards


def _first_line(value: str) -> str:
    for line in value.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.upper())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _calendar_date(value: str) -> date:
    match = _DATE.fullmatch(value.strip())
    if match is None:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    month = _MONTHS.get(match[2].strip(".").lower())
    if month is None:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    try:
        return date(int(match[3]), month, int(match[1]))
    except ValueError:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.") from None


def _score(value: str) -> float:
    if not _SCORE.fullmatch(value.strip()):
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    number = float(value.strip().replace(",", "."))
    if number > 100:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    return number


def _distance(value: str) -> tuple[str, float]:
    match = _DISTANCE.fullmatch(value.strip())
    if match is None:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    number = float(match[1].replace(",", "."))
    if number < 0:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    canonical = f"{number:.4f}".rstrip("0").rstrip(".")
    return canonical, number


def _clock(value: str) -> time:
    match = _CLOCK.fullmatch(value.strip())
    if match is None:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    try:
        return time(int(match[1]), int(match[2]))
    except ValueError:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.") from None


def _duration(value: str) -> int:
    match = _DURATION.fullmatch(value.strip())
    if match is None:
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    return (int(match[1]) * 60 + int(match[2])) * 60


def _label(value: str) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) < 3 or _CLOCK.fullmatch(cleaned):
        raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.")
    return cleaned


def _paris_datetime(day: date, clock: time, zone: ZoneInfo) -> datetime:
    wall = datetime.combine(day, clock)
    candidates = []
    for fold in (0, 1):
        try:
            candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        except (OverflowError, ValueError):
            raise PhoneError("Carte de trajet non reconnue ; aucun import effectué.") from None
        if candidate.astimezone(zone).replace(tzinfo=None, fold=0) == wall:
            candidates.append(candidate)
    if len(set(candidates)) != 1:
        raise PhoneError("Heure de trajet ambiguë ou inexistante ; aucun import effectué.")
    return candidates[0]
