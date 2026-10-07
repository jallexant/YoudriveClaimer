from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from youdrive.models import Base


def open_database(path: Path) -> tuple[Engine, sessionmaker[Session]]:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path)))

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _ensure_column(connection, "claims", "gmail_draft_id", "VARCHAR")
        _ensure_column(connection, "trips", "reason", "TEXT")


def _ensure_column(connection, table: str, column: str, definition: str) -> None:
    rows = connection.execute(text(f"PRAGMA table_info({table})")).all()
    names = {row[1] for row in rows}
    if names and column not in names:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
