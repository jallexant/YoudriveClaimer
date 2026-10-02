import pytest

from youdrive.db.session import initialize_database, open_database


@pytest.fixture
def session(tmp_path):
    engine, sessions = open_database(tmp_path / "test.sqlite3")
    initialize_database(engine)
    with sessions() as session:
        yield session
    engine.dispose()
