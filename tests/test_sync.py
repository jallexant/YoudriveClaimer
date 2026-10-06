from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from youdrive.models import Claim, ClaimStatus, Trip
from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import PhoneTrip
from youdrive.services.sync import import_phone_trips


def trip(remote_id: str, score: float = 72) -> PhoneTrip:
    return PhoneTrip(
        remote_id, datetime(2026, 9, 30, 17, 2, tzinfo=UTC),
        datetime(2026, 9, 30, 17, 26, tzinfo=UTC), score, 8, 23 * 60,
        "Rue de la Paix, 75002 Paris", "Avenue Victor Hugo, 75016 Paris",
    )


def test_import_updates_score_and_keeps_claim_and_web_rows(session):
    session.add(Trip(
        youdrive_id="web-visible:abc", started_at=datetime(2026, 9, 1, tzinfo=UTC), score=90,
    ))
    existing = Trip(
        youdrive_id="phone:same", started_at=datetime(2026, 9, 30, 17, 2, tzinfo=UTC), score=70,
    )
    session.add(existing)
    session.flush()
    session.add(Claim(trip_id=existing.id, status=ClaimStatus.DRAFT, text="déjà préparé"))
    session.commit()
    added, updated = import_phone_trips(session, [trip("phone:same", 64), trip("phone:new")])
    session.commit()
    assert (added, updated) == (1, 1)
    rows = list(session.scalars(select(Trip).order_by(Trip.youdrive_id)))
    assert [row.youdrive_id for row in rows] == ["phone:new", "phone:same", "web-visible:abc"]
    kept = session.scalar(select(Trip).where(Trip.youdrive_id == "phone:same"))
    assert kept.score == 64
    assert kept.claim.text == "déjà préparé"
    assert kept.gps["start_label"] == "Rue de la Paix, 75002 Paris"


def test_duplicate_batch_imports_nothing(session):
    with pytest.raises(PhoneError, match="dupliquée"):
        import_phone_trips(session, [trip("phone:same"), trip("phone:same", 80)])
    session.rollback()
    assert session.scalar(select(Trip.id)) is None
