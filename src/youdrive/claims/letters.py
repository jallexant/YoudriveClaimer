"""Claim shaped like the insurer form reply. Nothing is sent."""

import re
from email.message import EmailMessage
from html import escape
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from youdrive.claims.errors import GmailError
from youdrive.config import Settings
from youdrive.models import Trip

CLAIM_TO = "servicetechniqueyoudrive@directassurance.fr"
_CONTRACT = re.compile(r"[0-9A-Za-z-]{1,32}")
_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
)
_SCREENSHOT = re.compile(r"[0-9a-f]{64}\.png")
_IMAGE_CID = "trajet@youdrive"
_DISPLAY_WIDTH = 600


def require_contract(settings: Settings) -> str:
    if _CONTRACT.fullmatch(settings.contract_number) is None:
        raise GmailError("Numéro de contrat manquant.")
    return settings.contract_number


def build_message(settings: Settings, trip: Trip) -> tuple[EmailMessage, str]:
    contract = require_contract(settings)
    capture = _screenshot_path(settings, trip)
    text = _plain(settings, trip, contract)
    message = EmailMessage()
    message["To"] = CLAIM_TO
    message["Subject"] = f"[Formulaire appli] n°{contract}"
    message.set_content(text, charset="utf-8")
    if capture is not None:
        fitted = _fitted_png(capture.read_bytes())
        width = (_png_size(fitted) or (_DISPLAY_WIDTH, 0))[0]
        message.add_alternative(
            _html(settings, trip, contract, width), subtype="html", charset="utf-8",
        )
        message.get_payload()[1].add_related(
            fitted, maintype="image", subtype="png",
            cid=f"<{_IMAGE_CID}>", disposition="inline",
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


def _plain(settings: Settings, trip: Trip, contract: str) -> str:
    text = "\n\n".join(_paragraphs(settings, trip, contract))
    signature = settings.mail_signature.strip()
    if signature:
        text += f"\n\n-- \n{signature}"
    return text


def _fitted_png(data: bytes) -> bytes:
    size = _png_size(data)
    if size is None or size[0] <= _DISPLAY_WIDTH:
        return data
    with Image.open(BytesIO(data)) as image:
        height = round(image.height * _DISPLAY_WIDTH / image.width)
        fitted = image.resize((_DISPLAY_WIDTH, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        fitted.save(output, format="PNG")
        return output.getvalue()


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _html(settings: Settings, trip: Trip, contract: str, image_width: int) -> str:
    paragraphs = [
        f"<p>{escape(paragraph)}</p>" for paragraph in _paragraphs(settings, trip, contract)
    ]
    image = (
        f'<p><img src="cid:{_IMAGE_CID}" alt="Détail du trajet" width="{image_width}" '
        f'style="display:block;width:100%;max-width:{image_width}px;height:auto;"></p>'
    )
    paragraphs.append(image)
    signature = settings.mail_signature.strip()
    if signature:
        paragraphs.append(f"<p>-- <br>{escape(signature).replace(chr(10), '<br>')}</p>")
    return "<html><body>" + "".join(paragraphs) + "</body></html>"


def _paragraphs(settings: Settings, trip: Trip, contract: str) -> list[str]:
    local = trip.started_at.astimezone(ZoneInfo(settings.timezone))
    when = f"{local.day} {_MONTHS[local.month - 1].capitalize()} à {local:%H:%M}"
    return [
        f"Mon numéro de contrat : {contract}",
        "Bonjour,",
        "Veuillez compléter votre demande en précisant la date et l’heure du trajet "
        "concerné par votre demande",
        f"Trajet du {when}.",
    ]
