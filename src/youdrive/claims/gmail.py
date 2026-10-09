"""Create Gmail drafts and send messages, then apply one label."""

import base64
import json
import logging
import os
import webbrowser
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path

from youdrive.claims.errors import GmailError
from youdrive.config import Settings

COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
SCOPES = (COMPOSE_SCOPE, MODIFY_SCOPE)
LABEL_NAME = "adm-voitures-toyota-assurance"
_CONSENT_BROWSER = "youdrive-gmail"
_CONSENT_TIMEOUT_SECONDS = 300
_SUCCESS_PAGE = "Connexion Gmail enregistrée. Vous pouvez fermer cette fenêtre."


def token_path(settings: Settings) -> Path:
    return settings.db_path.parent / "gmail-token.json"


def granted_scopes(settings: Settings) -> set[str]:
    path = token_path(settings)
    if not path.is_file():
        return set()
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set()
    scopes = info.get("scopes") if isinstance(info, dict) else None
    if not isinstance(scopes, list):
        return set()
    return {item for item in scopes if isinstance(item, str)}


def needs_reconnect(settings: Settings) -> bool:
    """A saved token without the label scope must be granted again."""
    if not token_path(settings).is_file():
        return False
    return not set(SCOPES).issubset(granted_scopes(settings))


def login(settings: Settings, on_url: Callable[[str], None] | None = None) -> None:
    if settings.gmail_client_file is None or not settings.gmail_client_file.is_file():
        raise GmailError("Fichier client Gmail manquant.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError
    except ImportError:
        raise GmailError("Dépendances Gmail absentes.") from None
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.gmail_client_file), list(SCOPES),
        )
        credentials = _run_consent(flow, on_url)
    except GmailError:
        raise
    except WSGITimeoutError:
        raise GmailError("La page Google n'a pas été confirmée. Réessayez.") from None
    except Exception:
        raise GmailError("Connexion Gmail refusée.") from None
    path = token_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")


class _ConsentBrowser(webbrowser.BaseBrowser):
    """Report the Google page instead of opening a window from this process.

    The screen often runs as a Windows service (session 0). That process has
    no desktop, so the system browser never appears for the signed-in user.
    """

    def __init__(self, on_url: Callable[[str], None] | None) -> None:
        super().__init__()
        self._on_url = on_url
        self._real = None
        if on_url is not None or not _interactive_session():
            return
        try:
            self._real = webbrowser.get()
        except webbrowser.Error:
            self._real = None

    def open(self, url, new=0, autoraise=True):
        if self._on_url is not None:
            self._on_url(url)
            return True
        print("Ouvrez cette page pour autoriser Gmail :")
        print(url)
        if self._real is not None:
            try:
                self._real.open(url, new=1, autoraise=True)
            except Exception:
                logging.getLogger("youdrive").error("gmail.browser_failed")
        return True


def _run_consent(flow, on_url: Callable[[str], None] | None):
    webbrowser.register(_CONSENT_BROWSER, None, _ConsentBrowser(on_url))
    # register() also adds the name to the default browser list. Keep it out
    # so a later webbrowser.open still uses the real browser.
    order = webbrowser._tryorder
    if order is not None:
        webbrowser._tryorder = [name for name in order if name.lower() != _CONSENT_BROWSER]
    return flow.run_local_server(
        port=0,
        open_browser=True,
        browser=_CONSENT_BROWSER,
        prompt="consent",
        authorization_prompt_message="",
        success_message=_SUCCESS_PAGE,
        timeout_seconds=_CONSENT_TIMEOUT_SECONDS,
    )


def _interactive_session() -> bool:
    if os.name != "nt":
        return True
    import ctypes
    session = ctypes.c_uint()
    ok = ctypes.windll.kernel32.ProcessIdToSessionId(
        ctypes.windll.kernel32.GetCurrentProcessId(),
        ctypes.byref(session),
    )
    if not ok:
        return True
    return session.value != 0


def create_draft(settings: Settings, message: EmailMessage, service=None) -> str:
    if service is None:
        service = _service(settings)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    label_id = ensure_label(service)
    try:
        created = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}},
        ).execute()
    except GmailError:
        raise
    except Exception:
        raise GmailError("Brouillon refusé.") from None
    draft_id = created.get("id") if isinstance(created, dict) else None
    nested = created.get("message") if isinstance(created, dict) else None
    message_id = nested.get("id") if isinstance(nested, dict) else None
    if not isinstance(draft_id, str) or not draft_id or len(draft_id) > 256:
        raise GmailError("Brouillon refusé.")
    if not isinstance(message_id, str) or not message_id:
        raise GmailError("Brouillon refusé.")
    _apply_label(service, message_id, label_id)
    return draft_id


def send_message(settings: Settings, message: EmailMessage, service=None) -> str:
    if service is None:
        service = _service(settings)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    label_id = ensure_label(service)
    try:
        sent = service.users().messages().send(
            userId="me", body={"raw": raw},
        ).execute()
    except GmailError:
        raise
    except Exception:
        raise GmailError("Envoi refusé.") from None
    message_id = sent.get("id") if isinstance(sent, dict) else None
    if not isinstance(message_id, str) or not message_id or len(message_id) > 256:
        raise GmailError("Envoi refusé.")
    try:
        _apply_label(service, message_id, label_id)
    except GmailError:
        logging.getLogger("youdrive").error("gmail.label_failed")
    return message_id


def _label_key(name: str) -> str:
    """Gmail treats ADM/Voitures/Toyota/Assurance as adm-voitures-toyota-assurance."""
    return name.replace("/", "-").casefold()


def _matching_label_id(listed, name: str) -> str | None:
    labels = listed.get("labels") if isinstance(listed, dict) else None
    if not isinstance(labels, list):
        return None
    wanted = _label_key(name)
    nested = None
    for label in labels:
        if not isinstance(label, dict):
            continue
        label_name = label.get("name")
        label_id = label.get("id")
        if not isinstance(label_name, str) or not isinstance(label_id, str) or not label_id:
            continue
        if label_name == name:
            return label_id
        if nested is None and _label_key(label_name) == wanted:
            nested = label_id
    return nested


def ensure_label(service, name: str = LABEL_NAME) -> str:
    try:
        listed = service.users().labels().list(userId="me").execute()
    except GmailError:
        raise
    except Exception:
        raise GmailError("Reconnectez Gmail pour autoriser le libellé.") from None
    found = _matching_label_id(listed, name)
    if found:
        return found
    try:
        created = service.users().labels().create(
            userId="me",
            body={
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        ).execute()
    except GmailError:
        raise
    except Exception:
        raise GmailError("Libellé Gmail refusé.") from None
    label_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(label_id, str) or not label_id:
        raise GmailError("Libellé Gmail refusé.")
    return label_id


def _apply_label(service, message_id: str, label_id: str) -> None:
    try:
        service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [label_id]},
        ).execute()
    except GmailError:
        raise
    except Exception:
        raise GmailError("Libellé Gmail refusé.") from None


def _service(settings: Settings):
    path = token_path(settings)
    if needs_reconnect(settings):
        raise GmailError("Reconnectez Gmail pour autoriser l'envoi et le libellé.")
    if not path.is_file():
        raise GmailError("Connexion Gmail requise.")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise GmailError("Dépendances Gmail absentes.") from None
    try:
        credentials = Credentials.from_authorized_user_file(str(path), list(SCOPES))
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                path.write_text(credentials.to_json(), encoding="utf-8")
            else:
                raise GmailError("Connexion Gmail requise.")
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)
    except GmailError:
        raise
    except Exception:
        raise GmailError("Connexion Gmail requise.") from None
