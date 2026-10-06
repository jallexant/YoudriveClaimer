import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/youdrive.sqlite3")
    daily_claim_limit: int = 3
    timezone: str = "Europe/Paris"
    log_level: str = "INFO"
    contract_number: str = ""
    mail_signature: str = ""
    gmail_client_file: Path | None = None

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
        )
