"""Read the same limited trip feed as the official PC portal."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ORIGIN = "https://espace-personnel.direct-assurance.fr"
LOGIN_URL = f"{ORIGIN}/espace-personnel/connexion"
SESSION_FILE = Path("data/web-session.json")
TRIP_PATH = re.compile(r"/api/private-domain-redesign/youdrive/policy/([^/]+)/trips")


class WebError(Exception):
    """Messages are fixed and safe to show, unlike browser exception payloads."""


@dataclass(frozen=True)
class WebTrip:
    remote_id: str
    started_at: datetime
    ended_at: datetime | None
    score: float | None
    distance_km: float | None
    duration_seconds: int | None


def validate_trip_url(url: str) -> str:
    parts = urlsplit(url)
    match = TRIP_PATH.fullmatch(parts.path)
    query = parse_qs(parts.query, keep_blank_values=True)
    if (
        parts.scheme != "https" or parts.netloc != "espace-personnel.direct-assurance.fr"
        or not match or parts.fragment or query != {"numberOfTrips": ["13"]}
    ):
        raise WebError("Adresse de récupération non conforme au parcours web observé.")
    return hashlib.sha256(match[1].encode()).hexdigest()[:20]


def _date(value: object) -> datetime:
    if not isinstance(value, str):
        raise WebError("Format de date web non reconnu ; aucun import effectué.")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise WebError("Format de date web non reconnu ; aucun import effectué.") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise WebError("Fuseau absent des dates web ; aucun import effectué.")
    return result.astimezone(UTC)


def _number(value: object, maximum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebError("Valeur numérique web non reconnue ; aucun import effectué.")
    if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise WebError("Valeur numérique web hors limites ; aucun import effectué.")
    return float(value)


def parse_trips(payload: object, scope: str) -> list[WebTrip]:
    if not isinstance(payload, dict) or type(payload.get("status")) is not int:
        raise WebError("Réponse web non reconnue ; aucun import effectué.")
    if payload["status"] == 3:
        raise WebError("Session expirée : relancez python -m youdrive login.")
    if payload["status"] != 0 or not isinstance(payload.get("data"), list):
        raise WebError("Le portail n'a pas fourni de liste de trajets exploitable.")
    if len(payload["data"]) > 13:
        raise WebError("Volume web inattendu ; vérifier le protocole avant import.")
    trips = []
    seen = set()
    for row in payload["data"]:
        if not isinstance(row, dict) or not {"id", "startDate", "endDate", "score",
                                            "distance", "durationInMinutes"} <= row.keys():
            raise WebError("Schéma de trajet web non reconnu ; aucun import effectué.")
        remote_id = row["id"]
        if type(remote_id) not in (str, int) or not str(remote_id).strip():
            raise WebError("Identifiant de trajet web non reconnu.")
        remote_id = f"web:{scope}:{remote_id}"
        if remote_id in seen:
            raise WebError("Identifiant dupliqué dans la réponse web ; aucun import effectué.")
        seen.add(remote_id)
        started_at = _date(row["startDate"])
        ended_at = _date(row["endDate"]) if row["endDate"] is not None else None
        if ended_at is not None and ended_at < started_at:
            raise WebError("Dates web incohérentes ; aucun import effectué.")
        minutes = _number(row["durationInMinutes"])
        seconds = round(minutes * 60) if minutes is not None else None
        trips.append(WebTrip(remote_id, started_at, ended_at, _number(row["score"], 100),
                             _number(row["distance"]), seconds))
    return trips


def _load_session(path: Path) -> dict:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        validate_trip_url(saved["trip_url"])
        if saved["version"] != 1 or not isinstance(saved["storage_state"], dict):
            raise ValueError
        return saved
    except FileNotFoundError:
        raise WebError("Connexion initiale requise : lancez python -m youdrive login.") from None
    except (ValueError, TypeError, KeyError):
        raise WebError("Session locale invalide : relancez python -m youdrive login.") from None


def _save_session(path: Path, url: str, state: dict) -> None:
    validate_trip_url(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "trip_url": url, "storage_state": state}),
                         encoding="utf-8")
    temporary.replace(path)


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise WebError("Installez le connecteur : python -m pip install -e '.[web]'.") from None
    return sync_playwright


def login(path: Path = SESSION_FILE, timeout_seconds: int = 600) -> list[WebTrip]:
    """User signs in normally; capture only the trip GET generated by the portal."""
    sync_playwright = _playwright()
    try:
        previous = _load_session(path) if path.exists() else None
    except WebError:
        # Explicit login can replace invalid state after a successful connection.
        previous = None
    captured = []
    failures = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            try:
                context = browser.new_context(
                    storage_state=previous["storage_state"] if previous else None,
                    locale="fr-FR", timezone_id="Europe/Paris",
                )

                def capture(response):
                    parts = urlsplit(response.url)
                    if parts.netloc != "espace-personnel.direct-assurance.fr" or not (
                        TRIP_PATH.fullmatch(parts.path)
                    ) or response.request.method != "GET":
                        return
                    try:
                        scope = validate_trip_url(response.url)
                        if previous and scope != validate_trip_url(previous["trip_url"]):
                            raise WebError(
                                "Contrat différent de la session locale ; import arrêté.",
                            )
                        if response.status != 200:
                            raise WebError("Le portail a refusé la récupération des trajets.")
                        trips = parse_trips(response.json(), scope)
                        captured.append((response.url, trips))
                    except WebError as exc:
                        failures.append(exc)
                    except Exception:
                        failures.append(WebError("Réponse web illisible ; aucun import effectué."))

                context.on("response", capture)
                page = context.new_page()
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                print("Dans Chrome, connectez-vous à Direct Assurance, sélectionnez votre contrat "
                      "puis TABLEAU DE BORD YOUDRIVE. Délai : 10 minutes.", flush=True)
                deadline = datetime.now(UTC).timestamp() + timeout_seconds
                while not captured and not failures and datetime.now(UTC).timestamp() < deadline:
                    if page.is_closed():
                        raise WebError("Fenêtre fermée avant la récupération des trajets.")
                    page.wait_for_timeout(500)
                if failures:
                    raise failures[0]
                if not captured:
                    raise WebError("Aucune réponse de trajets observée dans le délai imparti.")
                url, trips = captured[0]
                _save_session(path, url, context.storage_state())
                return trips
            finally:
                browser.close()
    except (WebError, OSError):
        raise
    except Exception:
        raise WebError(
            "Connexion navigateur interrompue. Vérifiez Chrome et relancez login.",
        ) from None


def fetch_trips(path: Path = SESSION_FILE) -> list[WebTrip]:
    saved = _load_session(path)
    scope = validate_trip_url(saved["trip_url"])
    sync_playwright = _playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                context = browser.new_context(storage_state=saved["storage_state"])
                response = context.request.get(saved["trip_url"], timeout=60000, max_redirects=0)
                if response.status in (301, 302, 303, 307, 308, 401, 403):
                    raise WebError(
                        "Session refusée ou expirée : relancez python -m youdrive login.",
                    )
                if response.status != 200:
                    raise WebError("Service de trajets indisponible ; réessayez ultérieurement.")
                if "application/json" not in response.headers.get("content-type", ""):
                    raise WebError(
                        "Session web non exploitable : relancez python -m youdrive login.",
                    )
                trips = parse_trips(response.json(), scope)
                _save_session(path, saved["trip_url"], context.storage_state())
                return trips
            finally:
                browser.close()
    except (WebError, OSError):
        raise
    except Exception:
        raise WebError("Récupération web interrompue ; aucune donnée importée.") from None
