"""Plain-text claim shaped like the insurer form reply. Nothing is sent."""

import re
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from youdrive.claims.errors import GmailError
from youdrive.config import Settings
from youdrive.models import Trip

CLAIM_TO = "servicetechniqueyoudrive@directassurance.fr"
_CONTRACT = re.compile(r"[0-9A-Za-z-]{1,32}")
_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
)
_PLACEHOLDER = "[À compléter : ce qui ne correspond pas sur ce trajet]"
_SCREENSHOT = re.compile(r"[0-9a-f]{64}\.png")


def require_contract(settings: Settings) -> str:
    if _CONTRACT.fullmatch(settings.contract_number) is None:
        raise GmailError("Numéro de contrat manquant.")
    return settings.contract_number


def build_message(settings: Settings, trip: Trip) -> tuple[EmailMessage, str]:
    contract = require_contract(settings)
    capture = _screenshot_path(settings, trip)
    text = _body(settings, trip, contract, attached=capture is not None)
    message = EmailMessage()
    message["To"] = CLAIM_TO
    message["Subject"] = f"[Formulaire appli] n°{contract}"
    message.set_content(text, charset="utf-8")
    if capture is not None:
        message.add_attachment(
            capture.read_bytes(), maintype="image", subtype="png", filename="trajet.png",
        )
    return message, text


def _screenshot_path(settings: Settings, trip: Trip) -> Path | None:
    raw = trip.gps.get("screenshot") if isinstance(trip.gps, dict) else None
    if not isinstance(raw, str) or _SCREENSHOT.fullmatch(raw) is None:
        return None
    path = settings.db_path.parent / "screenshots" / raw
    if path.is_file():
        return path
    return None


def _body(settings: Settings, trip: Trip, contract: str, *, attached: bool) -> str:
    local = trip.started_at.astimezone(ZoneInfo(settings.timezone))
    when = f"{local.day} {_MONTHS[local.month - 1].capitalize()} à {local:%H:%M}"
    lines = [
        f"Mon numéro de contrat : {contract}",
        "",
        "Bonjour,",
        "",
        "Veuillez compléter votre demande en précisant la date et l’heure du trajet "
        "concerné par votre demande",
        "",
        f"Trajet du {when}.",
        "",
    ]
    if attached:
        lines.extend(["La capture du détail est jointe.", ""])
    lines.append(_PLACEHOLDER)
    signature = settings.mail_signature.strip()
    if signature:
        lines.extend(["", "-- ", signature])
    return "\n".join(lines)
