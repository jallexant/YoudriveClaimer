import base64
from datetime import UTC, datetime
from email import message_from_bytes
from io import BytesIO

import pytest
from sqlalchemy import select, text

from youdrive.claims.drafts import prepare_drafts
from youdrive.claims.errors import GmailError
from youdrive.claims.gmail import create_draft
from youdrive.claims.letters import build_message
from youdrive.config import Settings
from youdrive.db.session import initialize_database, open_database
from youdrive.models import Claim, ClaimStatus, Trip


def add_trip(session, remote_id, when, score=72):
    trip = Trip(
        youdrive_id=remote_id, started_at=when, ended_at=when, score=score,
        distance_km=8, duration_seconds=23 * 60,
    )
    session.add(trip)
    session.flush()
    return trip


def test_letter_uses_the_form_shape_without_inventing_a_reason():
    trip = Trip(
        youdrive_id="phone:letter", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC),
        score=72, distance_km=12.5, duration_seconds=23 * 60,
        gps={"start_label": "adresse privée"},
    )
    settings = Settings(contract_number="000", mail_signature="Signature locale")
    message, text = build_message(settings, trip)
    assert message["To"] == "servicetechniqueyoudrive@directassurance.fr"
    assert message["Subject"] == "[Formulaire appli] n°000"
    assert "Trajet du 26 Septembre à 14:58." in text
    assert "Score affiché" not in text
    assert "Distance" not in text
    assert "Durée" not in text
    assert "Signature locale" in text
    assert "adresse privée" not in text
    assert "régulateur" not in text
    assert "basse vitesse" not in text


def test_draft_shows_the_detail_capture_in_the_body(tmp_path):
    name = f"{'cd' * 32}.png"
    folder = tmp_path / "screenshots"
    folder.mkdir()
    (folder / name).write_bytes(b"\x89PNG\r\n\x1a\nsecret-image")
    trip = Trip(
        youdrive_id="phone:letter", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC),
        score=72, distance_km=8, duration_seconds=23 * 60,
        gps={"screenshot": name, "start_label": "adresse privée"},
    )
    settings = Settings(contract_number="000", db_path=tmp_path / "db.sqlite3")
    message, text = build_message(settings, trip)
    assert "adresse privée" not in text
    assert list(message.iter_attachments()) == []
    images = [part for part in message.walk() if part.get_content_type() == "image/png"]
    assert len(images) == 1
    assert images[0].get_content_disposition() == "inline"
    assert images[0]["Content-ID"] == "<trajet@youdrive>"
    assert images[0].get_payload(decode=True) == b"\x89PNG\r\n\x1a\nsecret-image"
    html = message.get_body(preferencelist=("html",)).get_content()
    assert 'src="cid:trajet@youdrive"' in html
    assert 'width="600"' in html
    assert "adresse privée" not in html
    outside = Trip(
        youdrive_id="phone:letter", started_at=trip.started_at, score=72,
        gps={"screenshot": "../secret.png"},
    )
    plain, body = build_message(settings, outside)
    assert plain.get_content_type() == "text/plain"
    assert "secret" not in body


def test_wide_capture_is_fitted_to_the_message_width(tmp_path):
    from PIL import Image

    name = f"{'ab' * 32}.png"
    folder = tmp_path / "screenshots"
    folder.mkdir()
    source = folder / name
    Image.new("RGB", (1008, 2244), "white").save(source, format="PNG")
    trip = Trip(
        youdrive_id="phone:wide", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC),
        score=72, gps={"screenshot": name},
    )
    message, _text = build_message(
        Settings(contract_number="000", db_path=tmp_path / "db.sqlite3"), trip,
    )
    payload = next(
        part for part in message.walk() if part.get_content_type() == "image/png"
    ).get_payload(decode=True)
    with Image.open(BytesIO(payload)) as fitted:
        assert fitted.size == (600, 1336)
    with Image.open(source) as original:
        assert original.size == (1008, 2244)


def test_missing_contract_is_rejected_without_calling_gmail(session):
    add_trip(session, "phone:one", datetime(2026, 9, 1, tzinfo=UTC))
    called = False

    def create(_message):
        nonlocal called
        called = True
        return "draft-1"

    with pytest.raises(GmailError, match="contrat manquant"):
        prepare_drafts(
            session, Settings(contract_number=""), datetime(2026, 10, 6, tzinfo=UTC), create,
        )
    assert called is False
    assert session.scalar(select(Claim.id)) is None


def test_only_the_oldest_three_candidates_are_prepared(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    trips = [
        add_trip(session, f"phone:{index}", datetime(2026, 9, index, tzinfo=UTC))
        for index in range(1, 5)
    ]
    add_trip(session, "phone:perfect", datetime(2026, 8, 1, tzinfo=UTC), score=100)
    made = prepare_drafts(
        session, Settings(contract_number="000", daily_claim_limit=3), now,
        lambda message: f"draft-{message['To']}",
    )
    assert made == 3
    claims = list(session.scalars(select(Claim).order_by(Claim.trip_id)))
    assert [claim.trip_id for claim in claims] == [trip.id for trip in trips[:3]]
    assert all(claim.sent_at is None and claim.status == ClaimStatus.DRAFT for claim in claims)
    assert "régulateur" not in claims[0].text
    assert session.scalar(select(Claim).where(Claim.trip_id == trips[3].id)) is None


def test_gmail_refusal_does_not_claim_that_trip(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    trips = [
        add_trip(session, f"phone:{index}", datetime(2026, 9, index, tzinfo=UTC))
        for index in range(1, 3)
    ]
    calls = []

    def create(_message):
        calls.append(1)
        if len(calls) == 2:
            raise GmailError("Brouillon refusé.")
        return "draft-1"

    with pytest.raises(GmailError, match="refusé"):
        prepare_drafts(session, Settings(contract_number="000"), now, create)
    claims = list(session.scalars(select(Claim)))
    assert len(claims) == 1
    assert claims[0].trip_id == trips[0].id
    assert claims[0].gmail_draft_id == "draft-1"
    assert claims[0].sent_at is None
    assert session.scalar(select(Claim).where(Claim.trip_id == trips[1].id)) is None


def test_drafts_already_created_today_fill_the_budget(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    for index in range(3):
        trip = add_trip(session, f"phone:old-{index}", datetime(2026, 8, index + 1, tzinfo=UTC))
        session.add(Claim(trip_id=trip.id, created_at=now))
    add_trip(session, "phone:waiting", datetime(2026, 9, 2, tzinfo=UTC))
    session.commit()
    called = False

    def create(_message):
        nonlocal called
        called = True
        return "draft-extra"

    made = prepare_drafts(
        session, Settings(contract_number="000"), now, create,
    )
    assert made == 0
    assert called is False


def test_create_draft_encodes_the_message_and_has_no_send_call():
    class Drafts:
        def __init__(self):
            self.body = None

        def create(self, userId, body):
            self.body = (userId, body)
            return self

        def execute(self):
            return {"id": "draft-1"}

    class Users:
        def __init__(self):
            self.drafts_api = Drafts()

        def drafts(self):
            return self.drafts_api

    class Service:
        def __init__(self):
            self.users_api = Users()

        def users(self):
            return self.users_api

    service = Service()
    message, _text = build_message(
        Settings(contract_number="000"),
        Trip(youdrive_id="phone:x", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC), score=70),
    )
    assert create_draft(Settings(), message, service) == "draft-1"
    user, body = service.users_api.drafts_api.body
    assert user == "me"
    decoded = message_from_bytes(base64.urlsafe_b64decode(body["message"]["raw"]))
    assert decoded["To"] == "servicetechniqueyoudrive@directassurance.fr"
    assert not hasattr(service, "send")


def test_existing_claims_table_gains_the_draft_column(tmp_path):
    engine, _sessions = open_database(tmp_path / "old.sqlite3")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE claims (id INTEGER PRIMARY KEY)"))
    initialize_database(engine)
    with engine.connect() as connection:
        names = {row[1] for row in connection.execute(text("PRAGMA table_info(claims)"))}
    engine.dispose()
    assert "gmail_draft_id" in names
