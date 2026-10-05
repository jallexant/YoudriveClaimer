"""Read trip history through the official Android client's own API.

The request shape comes from the installed application's Dart snapshot.
Trip history is one query without a page parameter. Login uses PKCE in the
system browser. The refresh token stays in the local data directory.
"""

import base64
import hashlib
import json
import math
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import winreg
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from youdrive.config import Settings

API_ORIGIN = "https://master-7rqtwti-dtlqboapsyb6y.eu-2.platformsh.site"
AUTH_ORIGIN = "https://login.direct-assurance.fr"
REDIRECT_URI = "fr.axa.youdrive://auth"
# Policy calls use the client literal beside /users/agg_scores. The prospect
# literal belongs to the separate prospect login branch.
APP_KEY = "youdrive_france"
SCOPE = "openid offline_access IdentityServerApi user_context"
POLICY_PATH = "/proxy/darwin/motorpartner?_format=json"
POLICY_BODY = b"{}"
APK_PATH = Path("research-private/apk/base.apk")
_ENV_NAME = "assets/flutter_assets/assets/env/.env.production"
_CLIENT_KEY = "LOGIN_SSO_WEB_VIEW_CLIENT_ID"
_MAX_BODY = 20_000_000
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class AndroidError(Exception):
    """Fixed messages only: responses can contain trips and tokens."""


class SessionRejected(AndroidError):
    def __init__(self) -> None:
        super().__init__("Session refusée.")


class AuthRejected(AndroidError):
    def __init__(self) -> None:
        super().__init__("Connexion refusée.")


@dataclass(frozen=True)
class AndroidTrip:
    remote_id: str
    started_at: datetime
    ended_at: datetime | None
    score: float | None
    distance_km: float | None
    duration_seconds: int | None
    events: list[dict]
    gps: dict | None


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass(frozen=True)
class SyncBatch:
    trips: list[AndroidTrip]
    policy_count: int


def trips_path(policy_id: str) -> str:
    quoted = urllib.parse.quote(policy_id, safe="")
    return (
        "/users/trips?_format=json&with_pois=true"
        f"&encrypted_policy_id={quoted}&with_invalid=true"
    )


def policy_ids(payload: object) -> list[str]:
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            value = node.get("EncryptedPolicyGeneralId")
            if isinstance(value, str) and value.strip():
                found.append(value.strip())
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(payload)
    unique: list[str] = []
    for value in found:
        if value not in unique:
            unique.append(value)
    return unique


def parse_trips(payload: object, timezone: str) -> list[AndroidTrip]:
    if isinstance(payload, dict) and payload.get("hasNextPage") is True:
        raise AndroidError("Liste incomplète sans pagination documentée ; aucun import effectué.")
    if not isinstance(payload, dict) or not isinstance(payload.get("trips"), list):
        raise AndroidError("Réponse de trajets non reconnue ; aucun import effectué.")
    zone = ZoneInfo(timezone)
    trips = [_trip(item, zone) for item in payload["trips"]]
    identities = [trip.remote_id for trip in trips]
    if len(identities) != len(set(identities)):
        raise AndroidError("Identité de trajet dupliquée ; aucun import effectué.")
    return trips


def build_authorize_url(client_id: str, challenge: str) -> str:
    query = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTH_ORIGIN}/connect/authorize?{query}"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def login(
    settings: Settings, *, transport: Transport | None = None, client_id: str | None = None,
    open_browser: Callable[[str], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    register: Callable[[Path], None] | None = None, timeout_seconds: float = 300,
) -> None:
    resolved_client = client_id if client_id is not None else _client_id()
    verifier, challenge = pkce_pair()
    data_dir = _data_dir(settings)
    callback = data_dir / "android-login-callback.txt"
    failure = data_dir / "android-login-callback-error.txt"
    callback.unlink(missing_ok=True)
    failure.unlink(missing_ok=True)
    (register or _register_protocol)(data_dir)
    print("Ouverture de la page de connexion officielle.")
    (open_browser or _open_browser)(build_authorize_url(resolved_client, challenge))
    print("Connectez-vous dans le navigateur. En attente du retour.")
    deadline = time.monotonic() + timeout_seconds
    while not callback.exists():
        if failure.exists():
            message = failure.read_text(encoding="utf-8").strip()
            failure.unlink(missing_ok=True)
            raise AndroidError(message or "Retour de connexion non reconnu.")
        if time.monotonic() >= deadline:
            raise AndroidError("Connexion non terminée. Relancez la commande login.")
        sleeper(0.5)
    returned = callback.read_text(encoding="utf-8")
    callback.unlink(missing_ok=True)
    tokens = _exchange({
        "grant_type": "authorization_code",
        "code": _authorization_code(returned),
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "client_id": resolved_client,
    }, transport or _urllib_transport)
    _save_session(settings, tokens)


def accept_callback(url: str | None, directory: Path) -> None:
    if url is None:
        raise AndroidError("Retour de connexion non reconnu.")
    text = _callback_text(url)
    target = directory / "android-login-callback.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def note_callback_error(directory: Path, message: str) -> None:
    target = directory / "android-login-callback-error.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(message, encoding="utf-8")


def synchronize(
    settings: Settings, *, transport: Transport | None = None, client_id: str | None = None,
    open_browser: Callable[[str], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    register: Callable[[Path], None] | None = None,
) -> SyncBatch:
    client = transport or _urllib_transport
    resolved_client = client_id if client_id is not None else _client_id()
    tokens = _usable_session(
        settings, resolved_client, client, open_browser, sleeper, register,
    )
    try:
        policies = _request_json(client, tokens, "POST", POLICY_PATH, POLICY_BODY)
    except SessionRejected:
        login(
            settings, transport=client, client_id=resolved_client, open_browser=open_browser,
            sleeper=sleeper, register=register,
        )
        tokens = _load_session(settings)
        policies = _request_json(client, tokens, "POST", POLICY_PATH, POLICY_BODY)
    identifiers = policy_ids(policies)
    if not identifiers:
        raise AndroidError("Aucun contrat lisible ; aucun import effectué.")
    trips: list[AndroidTrip] = []
    for identifier in identifiers:
        payload = _request_json(client, tokens, "GET", trips_path(identifier), None)
        trips.extend(parse_trips(payload, settings.timezone))
    if len({trip.remote_id for trip in trips}) != len(trips):
        raise AndroidError("Identité de trajet dupliquée ; aucun import effectué.")
    return SyncBatch(trips, len(identifiers))


def _trip(item: object, zone: ZoneInfo) -> AndroidTrip:
    if not isinstance(item, dict):
        raise AndroidError("Trajet non reconnu ; aucun import effectué.")
    started_raw = item.get("start_time")
    if not isinstance(started_raw, str) or not started_raw.strip():
        raise AndroidError("Horodatage de trajet absent ; aucun import effectué.")
    started = _timestamp(started_raw, zone)
    ended_raw = item.get("stop_time")
    ended = None if ended_raw is None else _timestamp(ended_raw, zone)
    if ended is not None and ended < started:
        raise AndroidError("Fin de trajet antérieure au début ; aucun import effectué.")
    duration = None if ended is None else int((ended - started).total_seconds())
    return AndroidTrip(
        remote_id=f"android:{started_raw.strip()}",
        started_at=started,
        ended_at=ended,
        score=_score(item.get("score")),
        distance_km=_distance(item.get("distance")),
        duration_seconds=duration,
        events=_pois(item.get("poi_dil")),
        gps=_gps(item),
    )


def _timestamp(value: object, zone: ZoneInfo) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise AndroidError("Horodatage de trajet non reconnu ; aucun import effectué.")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise AndroidError("Horodatage de trajet non reconnu ; aucun import effectué.") from None
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed.astimezone(UTC)
    wall = parsed.replace(tzinfo=None)
    candidates = []
    for fold in (0, 1):
        try:
            candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        except (OverflowError, ValueError):
            raise AndroidError(
                "Horodatage de trajet hors limites ; aucun import effectué.",
            ) from None
        if candidate.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.append(candidate)
    if len(set(candidates)) != 1:
        raise AndroidError("Horodatage de trajet ambigu ou inexistant ; aucun import effectué.")
    return candidates[0]


def _score(value: object) -> float | None:
    if value is None:
        return None
    number = _number(value)
    if number < 0 or number > 100:
        raise AndroidError("Score hors limites ; aucun import effectué.")
    return number


def _distance(value: object) -> float | None:
    if value is None:
        return None
    number = _number(value)
    if number < 0:
        raise AndroidError("Distance hors limites ; aucun import effectué.")
    return number


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise AndroidError("Valeur numérique non reconnue ; aucun import effectué.")
    return float(value)


def _pois(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AndroidError("Points d'intérêt non reconnus ; aucun import effectué.")
    return [dict(item) for item in value]


def _gps(item: dict) -> dict:
    result = {}
    for key, target in (
        ("start_location", "start"), ("end_location", "end"), ("scores_dil", "scores"),
    ):
        value = item.get(key)
        if value is None:
            continue
        if not isinstance(value, dict):
            raise AndroidError("Détail de trajet non reconnu ; aucun import effectué.")
        result[target] = value
    for key in ("status", "status_detail"):
        value = item.get(key)
        if isinstance(value, str):
            result[key] = value
    return result


def _callback_text(url: str) -> str:
    text = url.strip().strip("\"'")
    if len(text) > 16384:
        raise AndroidError("Retour de connexion non reconnu.")
    start = text.lower().find("fr.axa.youdrive://")
    if start < 0:
        raise AndroidError("Retour de connexion non reconnu.")
    text = text[start:]
    parts = urllib.parse.urlsplit(text)
    if parts.scheme.lower() != "fr.axa.youdrive" or parts.netloc.lower() != "auth":
        raise AndroidError("Retour de connexion non reconnu.")
    if parts.path not in ("", "/"):
        raise AndroidError("Retour de connexion non reconnu.")
    return text


def _authorization_code(url: str) -> str:
    parts = urllib.parse.urlsplit(_callback_text(url))
    params = urllib.parse.parse_qs(parts.query)
    if "code" not in params and parts.fragment:
        params = urllib.parse.parse_qs(parts.fragment)
    code = params.get("code", [""])[0]
    if not code or len(code) > 8192:
        raise AndroidError("Code de connexion absent.")
    return code


def _exchange(form: dict[str, str], transport: Transport) -> SessionTokens:
    status, payload = transport(
        "POST", f"{AUTH_ORIGIN}/connect/token",
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        urllib.parse.urlencode(form).encode("ascii"),
    )
    if status in (400, 401):
        raise AuthRejected
    if status != 200:
        raise AndroidError(f"Connexion interrompue (statut {status}).")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        raise AndroidError("Réponse de connexion non reconnue.") from None
    if not isinstance(parsed, dict):
        raise AndroidError("Réponse de connexion non reconnue.")
    access = parsed.get("access_token")
    refresh = parsed.get("refresh_token")
    expires = parsed.get("expires_in")
    if not isinstance(access, str) or not isinstance(refresh, str) or isinstance(expires, bool):
        raise AndroidError("Jetons de connexion incomplets.")
    if not isinstance(expires, int) or expires < 1:
        raise AndroidError("Durée de session non reconnue.")
    return SessionTokens(access, refresh, _expiry(expires))


def _expiry(expires_in: int) -> datetime:
    return datetime.fromtimestamp(time.time() + expires_in - 30, UTC)


def _usable_session(
    settings: Settings, client_id: str, transport: Transport,
    open_browser: Callable[[str], None] | None, sleeper: Callable[[float], None],
    register: Callable[[Path], None] | None,
) -> SessionTokens:
    if not _session_file(settings).exists():
        print("Session absente. Ouverture de la connexion.")
        login(
            settings, transport=transport, client_id=client_id, open_browser=open_browser,
            sleeper=sleeper, register=register,
        )
        return _load_session(settings)
    tokens = _load_session(settings)
    if tokens.expires_at > datetime.now(UTC):
        return tokens
    try:
        refreshed = _exchange({
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "client_id": client_id,
        }, transport)
    except AuthRejected:
        print("Session refusée. Ouverture de la connexion.")
        login(
            settings, transport=transport, client_id=client_id, open_browser=open_browser,
            sleeper=sleeper, register=register,
        )
        return _load_session(settings)
    _save_session(settings, refreshed)
    return refreshed


def _request_json(
    transport: Transport, tokens: SessionTokens, method: str, path: str, body: bytes | None,
) -> object:
    headers = _api_headers(tokens)
    if body is not None:
        headers["Content-Type"] = "application/json"
    status, payload = transport(method, f"{API_ORIGIN}{path}", headers, body)
    if status == 401:
        raise SessionRejected
    if status != 200:
        detail = _safe_server_message(payload)
        if detail:
            raise AndroidError(f"Lecture interrompue (statut {status}) : {detail}")
        raise AndroidError(f"Lecture interrompue (statut {status}).")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        raise AndroidError("Réponse illisible ; aucun import effectué.") from None


def _safe_server_message(payload: bytes) -> str | None:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    message = parsed.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 180 or "@" in message:
        return None
    return message.strip()


def _api_headers(tokens: SessionTokens) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens.access_token}",
        "X-AppKey": APP_KEY,
        "X-Axa-TargetServer": "prod",
        "Accept": "application/json",
    }


def _client_id() -> str:
    if not APK_PATH.is_file():
        raise AndroidError("APK locale introuvable. L'extraction déjà réalisée est requise.")
    try:
        with zipfile.ZipFile(APK_PATH) as archive:
            text = archive.read(_ENV_NAME).decode("utf-8")
    except (OSError, KeyError, UnicodeError, zipfile.BadZipFile):
        raise AndroidError("Client de connexion illisible dans l'APK locale.") from None
    for line in text.splitlines():
        if line.startswith(f"{_CLIENT_KEY}="):
            value = line.split("=", 1)[1].strip().strip("\"'")
            if value:
                return value
    raise AndroidError("Client de connexion absent de l'APK locale.")


def _session_file(settings: Settings) -> Path:
    return _data_dir(settings) / "android-session.json"


def _data_dir(settings: Settings) -> Path:
    directory = settings.db_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _save_session(settings: Settings, tokens: SessionTokens) -> None:
    _session_file(settings).write_text(json.dumps({
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at.isoformat(),
    }), encoding="utf-8")


def _load_session(settings: Settings) -> SessionTokens:
    try:
        payload = json.loads(_session_file(settings).read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(payload["expires_at"])
        if expires.tzinfo is None:
            raise ValueError
        return SessionTokens(payload["access_token"], payload["refresh_token"], expires)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise AndroidError("Session locale illisible. Relancez la commande login.") from None


def _register_protocol(directory: Path) -> None:
    resolved = str(directory.resolve())
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = str(pythonw if pythonw.is_file() else Path(sys.executable))
    if '"' in resolved or '"' in launcher:
        raise AndroidError("Chemin local incompatible avec le retour de connexion.")
    command = f'"{launcher}" -m youdrive auth-callback --directory "{resolved}" "%1"'
    base = r"Software\Classes\fr.axa.youdrive"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:YouDrive Auth")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    command_key = base + r"\shell\open\command"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def _open_browser(url: str) -> None:
    import webbrowser
    if not webbrowser.open(url):
        raise AndroidError("Impossible d'ouvrir le navigateur pour la connexion.")


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], data: bytes | None,
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_RejectRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read(_MAX_BODY + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(_MAX_BODY + 1)
        status = exc.code
    except urllib.error.URLError:
        raise AndroidError("Lecture impossible. Vérifiez la connexion réseau.") from None
    if len(body) > _MAX_BODY:
        raise AndroidError("Réponse trop volumineuse ; aucun import effectué.")
    return status, body


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AndroidError(f"Redirection refusée (statut {code}).")
