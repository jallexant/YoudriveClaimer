from pathlib import Path

from sqlalchemy import Engine, URL, create_engine, event
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
