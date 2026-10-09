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


class _Done:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Labels:
    def __init__(self, log, labels):
        self.log = log
        self.labels = labels

    def list(self, userId):
        self.log.append(("labels.list", userId))
        return _Done({"labels": self.labels})

    def create(self, userId, body):
        self.log.append(("labels.create", userId, body))
        return _Done({"id": "Label_new"})


class _Drafts:
    def __init__(self, log):
        self.log = log

    def create(self, userId, body):
        self.log.append(("drafts.create", userId, body))
        return _Done({"id": "draft-1", "message": {"id": "msg-1"}})


class _Messages:
    def __init__(self, log, fail_label=False):
        self.log = log
        self.fail_label = fail_label

    def send(self, userId, body):
        self.log.append(("messages.send", userId, body))
        return _Done({"id": "msg-sent"})

    def modify(self, userId, id, body):
        self.log.append(("messages.modify", id, body))
        if self.fail_label:
            raise RuntimeError("label refused")
        return _Done({"id": id})


class _Service:
    def __init__(self, labels=None, fail_label=False):
        self.log = []
        self.labels_api = _Labels(self.log, [] if labels is None else labels)
        self.drafts_api = _Drafts(self.log)
        self.messages_api = _Messages(self.log, fail_label)

    def users(self):
        return self

    def labels(self):
        return self.labels_api

    def drafts(self):
        return self.drafts_api

    def messages(self):
        return self.messages_api


def test_create_draft_encodes_the_message_and_applies_the_label():
    service = _Service([{"id": "Label_9", "name": "adm-voitures-toyota-assurance"}])
    message, _text = build_message(
        Settings(contract_number="000"),
        Trip(youdrive_id="phone:x", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC), score=70),
    )
    assert create_draft(Settings(), message, service) == "draft-1"
    kind, user, body = service.log[1]
    assert kind == "drafts.create"
    assert user == "me"
    decoded = message_from_bytes(base64.urlsafe_b64decode(body["message"]["raw"]))
    assert decoded["To"] == "servicetechniqueyoudrive@directassurance.fr"
    assert ("messages.send", "me", body) not in service.log
    assert ("messages.modify", "msg-1", {"addLabelIds": ["Label_9"]}) in service.log


def test_missing_label_is_created_before_the_draft():
    service = _Service([])
    message, _text = build_message(
        Settings(contract_number="000"),
        Trip(youdrive_id="phone:x", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC), score=70),
    )
    assert create_draft(Settings(), message, service) == "draft-1"
    created = next(item for item in service.log if item[0] == "labels.create")
    assert created[2]["name"] == "adm-voitures-toyota-assurance"
    assert ("messages.modify", "msg-1", {"addLabelIds": ["Label_new"]}) in service.log


def test_send_message_applies_the_label_and_keeps_the_id_if_the_label_fails():
    from youdrive.claims.gmail import send_message

    ready = _Service([{"id": "Label_9", "name": "adm-voitures-toyota-assurance"}])
    message, _text = build_message(
        Settings(contract_number="000"),
        Trip(youdrive_id="phone:x", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC), score=70),
    )
    assert send_message(Settings(), message, ready) == "msg-sent"
    assert any(item[0] == "messages.send" for item in ready.log)
    assert ("messages.modify", "msg-sent", {"addLabelIds": ["Label_9"]}) in ready.log
    assert not any(item[0] == "drafts.create" for item in ready.log)
    failed = _Service(
        [{"id": "Label_9", "name": "adm-voitures-toyota-assurance"}], fail_label=True,
    )
    assert send_message(Settings(), message, failed) == "msg-sent"


def test_saved_reason_follows_the_date_and_the_address_stays_out(tmp_path):
    name = f"{'ab' * 32}.png"
    folder = tmp_path / "screenshots"
    folder.mkdir()
    (folder / name).write_bytes(b"\x89PNG\r\n\x1a\nsecret-image")
    trip = Trip(
        youdrive_id="phone:letter", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC),
        score=72, gps={"screenshot": name, "start_label": "adresse privée"},
        reason="a < b\nc",
    )
    settings = Settings(
        contract_number="000", mail_signature="Signature locale", db_path=tmp_path / "db.sqlite3",
    )
    message, text = build_message(settings, trip)
    assert text.index("Trajet du 26 Septembre à 14:58.") < text.index("a < b")
    assert text.index("a < b") < text.index("Signature locale")
    assert "adresse privée" not in text
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "a &lt; b<br>c" in html
    assert html.index("a &lt; b") < html.index("<img")
    assert html.index("<img") < html.index("Signature locale")
    assert "adresse privée" not in html


def test_saved_reason_is_copied_and_the_address_stays_out(session):
    trip = add_trip(session, "phone:one", datetime(2026, 9, 1, tzinfo=UTC))
    trip.reason = "Défaut de vitesse"
    trip.gps = {"start_label": "adresse privée"}
    prepare_drafts(
        session, Settings(contract_number="000"), datetime(2026, 10, 6, tzinfo=UTC),
        lambda _message: "draft-1",
    )
    text = session.scalar(select(Claim.text))
    assert "Défaut de vitesse" in text
    assert "adresse privée" not in text


def test_capture_stays_out_of_the_mail_when_the_setting_is_off(tmp_path):
    name = f"{'cd' * 32}.png"
    folder = tmp_path / "screenshots"
    folder.mkdir()
    (folder / name).write_bytes(b"\x89PNG\r\n\x1a\nsecret-image")
    trip = Trip(
        youdrive_id="phone:letter", started_at=datetime(2026, 9, 26, 12, 58, tzinfo=UTC),
        score=72, gps={"screenshot": name},
    )
    message, text = build_message(
        Settings(contract_number="000", db_path=tmp_path / "db.sqlite3", attach_screenshot=False),
        trip,
    )
    assert [part for part in message.walk() if part.get_content_type() == "image/png"] == []
    assert "secret" not in text
    assert message.get_content_type() == "text/plain"


def test_send_records_the_mail_and_keeps_the_daily_cap(session):
    from youdrive.claims.drafts import send_messages

    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    trip = add_trip(session, "phone:send", datetime(2026, 9, 2, tzinfo=UTC))
    trip.reason = "Motif envoyé"
    made = send_messages(
        session, Settings(contract_number="000"), now,
        lambda _message: "msg-1", with_reason_only=True,
    )
    assert made == 1
    claim = session.scalar(select(Claim))
    assert claim is not None
    assert claim.status == ClaimStatus.PENDING
    assert claim.sent_at == now
    assert claim.gmail_draft_id is None
    assert "Motif envoyé" in claim.text
    waiting = add_trip(session, "phone:later", datetime(2026, 9, 3, tzinfo=UTC))
    waiting.reason = "Autre motif"
    made_again = send_messages(
        session, Settings(contract_number="000", daily_claim_limit=1), now,
        lambda _message: "msg-2", with_reason_only=True,
    )
    assert made_again == 0


def test_one_named_trip_is_prepared_on_its_own(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    older = add_trip(session, "phone:older", datetime(2026, 9, 1, tzinfo=UTC))
    older.reason = "Ancien motif"
    chosen = add_trip(session, "phone:chosen", datetime(2026, 9, 2, tzinfo=UTC))
    chosen.reason = "Motif de ce trajet"
    made = prepare_drafts(
        session, Settings(contract_number="000", daily_claim_limit=3), now,
        lambda _message: "draft-one", with_reason_only=True, only_id=chosen.id,
    )
    assert made == 1
    claim = session.scalar(select(Claim))
    assert claim is not None
    assert claim.trip_id == chosen.id
    assert "Motif de ce trajet" in claim.text
    assert session.scalar(select(Claim).where(Claim.trip_id == older.id)) is None


def test_named_trip_still_respects_the_daily_budget(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    filled = add_trip(session, "phone:filled", datetime(2026, 8, 1, tzinfo=UTC))
    session.add(Claim(trip_id=filled.id, created_at=now))
    waiting = add_trip(session, "phone:waiting", datetime(2026, 9, 2, tzinfo=UTC))
    waiting.reason = "Motif prêt"
    session.commit()
    called = False

    def create(_message):
        nonlocal called
        called = True
        return "draft-extra"

    made = prepare_drafts(
        session, Settings(contract_number="000", daily_claim_limit=1), now,
        create, with_reason_only=True, only_id=waiting.id,
    )
    assert made == 0
    assert called is False


def test_only_ready_reasons_are_prepared_oldest_first(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    skipped = add_trip(session, "phone:skip", datetime(2026, 9, 1, tzinfo=UTC))
    skipped.reason = "   "
    first = add_trip(session, "phone:first", datetime(2026, 9, 2, tzinfo=UTC))
    first.reason = "Défaut de vitesse"
    second = add_trip(session, "phone:second", datetime(2026, 9, 3, tzinfo=UTC))
    second.reason = "Virage lent"
    made = prepare_drafts(
        session, Settings(contract_number="000", daily_claim_limit=1), now,
        lambda _message: "draft-1", with_reason_only=True,
    )
    assert made == 1
    claim = session.scalar(select(Claim))
    assert claim is not None
    assert claim.trip_id == first.id
    assert "Défaut de vitesse" in claim.text
    assert session.scalar(select(Claim).where(Claim.trip_id == second.id)) is None
    assert session.scalar(select(Claim).where(Claim.trip_id == skipped.id)) is None


def test_existing_trips_table_gains_the_reason_column(tmp_path):
    engine, _sessions = open_database(tmp_path / "old-trips.sqlite3")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE trips (id INTEGER PRIMARY KEY, youdrive_id VARCHAR NOT NULL)"
        ))
    initialize_database(engine)
    with engine.connect() as connection:
        names = {row[1] for row in connection.execute(text("PRAGMA table_info(trips)"))}
    engine.dispose()
    assert "reason" in names


def test_existing_claims_table_gains_the_draft_column(tmp_path):
    engine, _sessions = open_database(tmp_path / "old.sqlite3")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE claims (id INTEGER PRIMARY KEY)"))
    initialize_database(engine)
    with engine.connect() as connection:
        names = {row[1] for row in connection.execute(text("PRAGMA table_info(claims)"))}
    engine.dispose()
    assert "gmail_draft_id" in names
