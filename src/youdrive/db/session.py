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
        rows = connection.execute(text("PRAGMA table_info(claims)")).all()
        names = {row[1] for row in rows}
        if names and "gmail_draft_id" not in names:
            connection.execute(text("ALTER TABLE claims ADD COLUMN gmail_draft_id VARCHAR"))
