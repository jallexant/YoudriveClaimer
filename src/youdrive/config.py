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

    def __post_init__(self) -> None:
        if self.daily_claim_limit < 1:
            raise ValueError("YOUDRIVE_DAILY_CLAIM_LIMIT doit être un entier positif.")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("YOUDRIVE_TIMEZONE doit être un fuseau IANA valide.") from exc
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("YOUDRIVE_LOG_LEVEL est invalide.")

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> "Settings":
        load_dotenv(env_file, override=False)
        try:
            limit = int(os.getenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "3"))
        except ValueError as exc:
            raise ValueError("YOUDRIVE_DAILY_CLAIM_LIMIT doit être un entier positif.") from exc
        return cls(
            db_path=Path(os.getenv("YOUDRIVE_DB_PATH", "data/youdrive.sqlite3")),
            daily_claim_limit=limit,
            timezone=os.getenv("YOUDRIVE_TIMEZONE", "Europe/Paris"),
            log_level=os.getenv("YOUDRIVE_LOG_LEVEL", "INFO").upper(),
        )
