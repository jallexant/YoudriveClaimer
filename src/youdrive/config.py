import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv, set_key


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/youdrive.sqlite3")
    daily_claim_limit: int = 3
    timezone: str = "Europe/Paris"
    log_level: str = "INFO"
    contract_number: str = ""
    mail_signature: str = ""
    gmail_client_file: Path | None = None
    attach_screenshot: bool = True

    def __post_init__(self) -> None:
        if self.daily_claim_limit < 1:
            raise ValueError("YOUDRIVE_DAILY_CLAIM_LIMIT doit être un entier positif.")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("YOUDRIVE_TIMEZONE doit être un fuseau IANA valide.") from exc
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("YOUDRIVE_LOG_LEVEL est invalide.")
        if len(self.mail_signature) > 4000:
            raise ValueError("YOUDRIVE_MAIL_SIGNATURE est trop longue.")

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> "Settings":
        load_dotenv(env_file, override=False)
        try:
            limit = int(os.getenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "3"))
        except ValueError as exc:
            raise ValueError("YOUDRIVE_DAILY_CLAIM_LIMIT doit être un entier positif.") from exc
        client = os.getenv("YOUDRIVE_GMAIL_CLIENT_FILE", "").strip()
        return cls(
            db_path=Path(os.getenv("YOUDRIVE_DB_PATH", "data/youdrive.sqlite3")),
            daily_claim_limit=limit,
            timezone=os.getenv("YOUDRIVE_TIMEZONE", "Europe/Paris"),
            log_level=os.getenv("YOUDRIVE_LOG_LEVEL", "INFO").upper(),
            contract_number=os.getenv("YOUDRIVE_CONTRACT_NUMBER", "").strip(),
            mail_signature=os.getenv("YOUDRIVE_MAIL_SIGNATURE", "").replace("\\n", "\n"),
            gmail_client_file=Path(client) if client else None,
            attach_screenshot=_enabled("YOUDRIVE_ATTACH_SCREENSHOT", True),
        )


_CONTRACT = re.compile(r"[0-9A-Za-z-]{1,32}")


def _enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "oui", "yes", "on"}


def save_preferences(
    env_file: Path, contract_number: str, mail_signature: str,
    daily_claim_limit: int, gmail_client_file: str, attach_screenshot: bool,
) -> None:
    """Write the fields edited from the local screen. Other keys stay in the file."""
    contract_number = contract_number.strip()
    if contract_number and _CONTRACT.fullmatch(contract_number) is None:
        raise ValueError("Numéro de contrat invalide.")
    mail_signature = mail_signature.replace("\r\n", "\n")
    client = gmail_client_file.strip()
    Settings(
        daily_claim_limit=daily_claim_limit,
        contract_number=contract_number,
        mail_signature=mail_signature,
        gmail_client_file=Path(client) if client else None,
        attach_screenshot=attach_screenshot,
    )
    env_file.parent.mkdir(parents=True, exist_ok=True)
    if not env_file.exists():
        env_file.write_text("", encoding="utf-8")
    path = str(env_file)
    stored_signature = mail_signature.replace("\n", "\\n")
    set_key(path, "YOUDRIVE_CONTRACT_NUMBER", contract_number, quote_mode="always")
    set_key(path, "YOUDRIVE_MAIL_SIGNATURE", stored_signature, quote_mode="always")
    set_key(path, "YOUDRIVE_DAILY_CLAIM_LIMIT", str(daily_claim_limit), quote_mode="never")
    set_key(path, "YOUDRIVE_GMAIL_CLIENT_FILE", client, quote_mode="always")
    set_key(
        path, "YOUDRIVE_ATTACH_SCREENSHOT", "1" if attach_screenshot else "0", quote_mode="never",
    )
