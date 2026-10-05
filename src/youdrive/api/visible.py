"""Validate displayed portal rows without reading credentials or private APIs."""

import math
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from youdrive.api.web import WebError, WebTrip

_MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12,
}
_FIELDS = {"date", "start", "end", "score", "distance", "duration", "identity"}
_DECIMAL = re.compile(r"[0-9]+(?:[,.][0-9]+)?")
_PARIS = ZoneInfo("Europe/Paris")


def _calendar_date(value: object) -> date:
    if not isinstance(value, str):
        raise WebError("Date visible non reconnue ; aucun import effectué.")
    match = re.fullmatch(r"([0-9]{1,2}) ([a-zéû]+) ([0-9]{4})", value.strip().lower())
    if match is None or match[2] not in _MONTHS:
        raise WebError("Date visible non reconnue ; aucun import effectué.")
    try:
        return date(int(match[3]), _MONTHS[match[2]], int(match[1]))
    except ValueError:
        raise WebError("Date visible invalide ; aucun import effectué.") from None


def _clock(value: object) -> time:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value.strip()):
        raise WebError("Heure visible non reconnue ; aucun import effectué.")
    try:
        hours, minutes = map(int, value.strip().split(":"))
        return time(hours, minutes)
    except ValueError:
        raise WebError("Heure visible invalide ; aucun import effectué.") from None


def _paris_datetime(day: date, clock: time) -> datetime:
    wall = datetime.combine(day, clock)
    candidates = []
    for fold in (0, 1):
        try:
            candidate = wall.replace(tzinfo=_PARIS, fold=fold).astimezone(UTC)
            if candidate.astimezone(_PARIS).replace(tzinfo=None) == wall:
                candidates.append(candidate)
        except (OverflowError, ValueError):
            raise WebError("Date visible hors limites ; aucun import effectué.") from None
    if len(set(candidates)) != 1:
        raise WebError("Heure visible ambiguë ou inexistante ; aucun import effectué.")
    return candidates[0]


def _decimal(value: object) -> float:
    if not isinstance(value, str) or len(value) > 128 or not _DECIMAL.fullmatch(value.strip()):
        raise WebError("Valeur numérique visible non reconnue ; aucun import effectué.")
    number = float(value.strip().replace(",", "."))
    if not math.isfinite(number) or number < 0:
        raise WebError("Valeur numérique visible hors limites ; aucun import effectué.")
    return number


def _score(value: object) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    number = _decimal(value)
    if number > 100:
        raise WebError("Score visible hors limites ; aucun import effectué.")
    return number


def _distance(value: object) -> float:
    if not isinstance(value, str) or len(value) > 128:
        raise WebError("Distance visible non reconnue ; aucun import effectué.")
    match = re.fullmatch(r"([0-9]+(?:[,.][0-9]+)?)\s+km", value.strip())
    if match is None:
        raise WebError("Distance visible non reconnue ; aucun import effectué.")
    return _decimal(match[1])


def _duration(value: object) -> int:
    if not isinstance(value, str):
        raise WebError("Durée visible non reconnue ; aucun import effectué.")
    match = re.fullmatch(r"([0-9]{1,6}):([0-5][0-9])", value.strip())
    if match is None:
        raise WebError("Durée visible non reconnue ; aucun import effectué.")
    return (int(match[1]) * 60 + int(match[2])) * 60


def parse_visible(payload: object) -> list[WebTrip]:
    if (
        not isinstance(payload, dict)
        or payload.get("source") != "direct-assurance-visible-v1"
        or payload.get("page") not in ("history", "dashboard")
        or not isinstance(payload.get("trips"), list)
    ):
        raise WebError("Capture visible non reconnue ; aucun import effectué.")
    maximum = 10 if payload["page"] == "history" else 3
    if len(payload["trips"]) > maximum:
        raise WebError("Nombre de trajets visibles inattendu ; aucun import effectué.")
    trips = []
    seen = set()
    for row in payload["trips"]:
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise WebError("Schéma de trajet visible non reconnu ; aucun import effectué.")
        identity = row["identity"]
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", identity):
            raise WebError("Identité visible non reconnue ; aucun import effectué.")
        identity = identity.lower()
        if identity in seen:
            raise WebError("Identité visible dupliquée ; aucun import effectué.")
        seen.add(identity)
        day = _calendar_date(row["date"])
        start = _clock(row["start"])
        end = _clock(row["end"])
        try:
            end_day = day + timedelta(days=1) if end < start else day
        except OverflowError:
            raise WebError("Date visible invalide ; aucun import effectué.") from None
        trips.append(WebTrip(
            remote_id=f"web-visible:{identity}",
            started_at=_paris_datetime(day, start),
            ended_at=_paris_datetime(end_day, end),
            score=_score(row["score"]), distance_km=_distance(row["distance"]),
            duration_seconds=_duration(row["duration"]),
        ))
    return trips
