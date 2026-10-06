"""Plain-text claim shaped like the insurer form reply. Nothing is sent."""

import re
from email.message import EmailMessage
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


def require_contract(settings: Settings) -> str:
    if _CONTRACT.fullmatch(settings.contract_number) is None:
        raise GmailError("Numéro de contrat manquant.")
    return settings.contract_number


def build_message(settings: Settings, trip: Trip) -> tuple[EmailMessage, str]:
    contract = require_contract(settings)
    text = _body(settings, trip, contract)
    message = EmailMessage()
    message["To"] = CLAIM_TO
    message["Subject"] = f"[Formulaire appli] n°{contract}"
    message.set_content(text, charset="utf-8")
    return message, text


def _body(settings: Settings, trip: Trip, contract: str) -> str:
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
        f"Score affiché : {_number(trip.score)}",
        "Distance : " + (
            "inconnue" if trip.distance_km is None else f"{_number(trip.distance_km)} km"
        ),
        f"Durée : {_duration(trip.duration_seconds)}",
        "",
        _PLACEHOLDER,
    ]
    signature = settings.mail_signature.strip()
    if signature:
        lines.extend(["", "-- ", signature])
    return "\n".join(lines)


def _number(value: float | None) -> str:
    if value is None:
        return "inconnue"
    return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _duration(seconds: int | None) -> str:
    if seconds is None:
        return "inconnue"
    minutes = seconds // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
