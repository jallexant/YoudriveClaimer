"""Create Gmail drafts. The compose scope can send; this module never does."""

import base64
from email.message import EmailMessage
from pathlib import Path

from youdrive.claims.errors import GmailError
from youdrive.config import Settings

SCOPE = "https://www.googleapis.com/auth/gmail.compose"


def token_path(settings: Settings) -> Path:
    return settings.db_path.parent / "gmail-token.json"


def login(settings: Settings) -> None:
    if settings.gmail_client_file is None or not settings.gmail_client_file.is_file():
        raise GmailError("Fichier client Gmail manquant.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise GmailError("Dépendances Gmail absentes.") from None
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.gmail_client_file), [SCOPE],
        )
        credentials = flow.run_local_server(port=0, open_browser=True)
    except GmailError:
        raise
    except Exception:
        raise GmailError("Connexion Gmail refusée.") from None
    path = token_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")


def create_draft(settings: Settings, message: EmailMessage, service=None) -> str:
    if service is None:
        service = _service(settings)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        created = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}},
        ).execute()
    except GmailError:
        raise
    except Exception:
        raise GmailError("Brouillon refusé.") from None
    draft_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(draft_id, str) or not draft_id or len(draft_id) > 256:
        raise GmailError("Brouillon refusé.")
    return draft_id


def _service(settings: Settings):
    path = token_path(settings)
    if not path.is_file():
        raise GmailError("Connexion Gmail requise.")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise GmailError("Dépendances Gmail absentes.") from None
    try:
        credentials = Credentials.from_authorized_user_file(str(path), [SCOPE])
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
