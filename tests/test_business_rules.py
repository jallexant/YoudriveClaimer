import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from youdrive.config import Settings, save_preferences
from youdrive.models import Claim, ClaimStatus, Trip
from youdrive.services.trips import (
    count_sent_today,
    list_candidates,
    mark_trip_handled,
    remaining_daily_budget,
    remaining_draft_budget,
    save_reason,
    summarize,
    update_claim,
)


def add_trip(session, remote_id, date, score=85):
    trip = Trip(youdrive_id=remote_id, started_at=date, score=score)
    session.add(trip)
    session.flush()
    return trip


def test_candidates_oldest_first_exclude_every_claim_and_unknown_score(session):
    oldest = add_trip(session, "fake-old", datetime(2026, 9, 1, tzinfo=UTC))
    newest = add_trip(session, "fake-new", datetime(2026, 9, 9, tzinfo=UTC))
    add_trip(session, "fake-perfect", datetime(2026, 8, 1, tzinfo=UTC), score=100)
    add_trip(session, "fake-unknown", datetime(2026, 8, 2, tzinfo=UTC), score=None)
    for index, status in enumerate(ClaimStatus):
        claimed = add_trip(session, f"fake-claimed-{index}", datetime(2026, 8, 3, tzinfo=UTC))
        session.add(Claim(trip_id=claimed.id, status=status))
    session.commit()
    assert [trip.id for trip in list_candidates(session)] == [oldest.id, newest.id]
    summary = summarize(session)
    assert summary.trips == 9
    assert summary.low_scores == 7
    assert summary.candidates == 2
    assert summary.claims == 5
    assert set(summary.statuses.values()) == {1}


def test_quota_counts_send_date_in_paris_and_never_goes_negative(session):
    dates = [
        datetime(2026, 10, 1, 21, 59, tzinfo=UTC),  # Oct 1, 23:59 local
        datetime(2026, 10, 1, 22, 0, tzinfo=UTC),   # Oct 2, midnight local
        datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        datetime(2026, 10, 2, 21, 59, tzinfo=UTC),
        datetime(2026, 10, 2, 22, 0, tzinfo=UTC),   # Oct 3, midnight local
        None,  # A draft is not sent
    ]
    for index, sent_at in enumerate(dates):
        trip = add_trip(session, f"fake-quota-{index}", datetime(2026, 9, 1, tzinfo=UTC))
        session.add(Claim(
            trip_id=trip.id, sent_at=sent_at,
            created_at=datetime(2026, 9, 2, tzinfo=UTC),
            status=ClaimStatus.CORRECTED if sent_at else ClaimStatus.DRAFT,
        ))
    session.commit()
    now = datetime(2026, 10, 2, 14, tzinfo=UTC)
    assert count_sent_today(session, now, "Europe/Paris") == 3
    assert remaining_daily_budget(session, Settings(), now) == 0
    assert remaining_daily_budget(session, Settings(daily_claim_limit=2), now) == 0
    assert remaining_daily_budget(session, Settings(daily_claim_limit=4), now) == 1


def test_quota_includes_full_25_hour_day_at_clock_change(session):
    trip = add_trip(session, "fake-clock", datetime(2026, 9, 1, tzinfo=UTC))
    session.add(Claim(trip_id=trip.id, sent_at=datetime(2026, 10, 25, 22, 30, tzinfo=UTC)))
    session.commit()
    assert count_sent_today(session, datetime(2026, 10, 25, 12, tzinfo=UTC), "Europe/Paris") == 1


def test_database_rejects_duplicate_claim(session):
    trip = add_trip(session, "fake-unique", datetime(2026, 9, 1, tzinfo=UTC))
    session.add(Claim(trip_id=trip.id))
    session.commit()
    session.add(Claim(trip_id=trip.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_database_rejects_duplicate_remote_id(session):
    add_trip(session, "fake-unique", datetime(2026, 9, 1, tzinfo=UTC))
    session.commit()
    with pytest.raises(IntegrityError):
        add_trip(session, "fake-unique", datetime(2026, 9, 2, tzinfo=UTC))
    session.rollback()


def test_database_rejects_nonexistent_trip(session):
    session.add(Claim(trip_id=999))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_dates_roundtrip_utc_and_reject_naive_date(session):
    trip = add_trip(session, "fake-aware", datetime(2026, 9, 1, tzinfo=UTC))
    session.commit()
    session.expire_all()
    assert trip.started_at == datetime(2026, 9, 1, tzinfo=UTC)
    with pytest.raises(StatementError):
        add_trip(session, "fake-naive", datetime(2026, 9, 1))
    session.rollback()


@pytest.mark.parametrize("kwargs", [
    {"score": -1}, {"score": 101}, {"distance_km": -1}, {"duration_seconds": -1},
    {"ended_at": datetime(2026, 8, 1, tzinfo=UTC)},
])
def test_database_rejects_invalid_trip_values(session, kwargs):
    session.add(Trip(youdrive_id="fake-invalid", started_at=datetime(2026, 9, 1, tzinfo=UTC),
                     **kwargs))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize("kwargs", [
    {"daily_claim_limit": 0}, {"daily_claim_limit": -1}, {"timezone": "Invalid/Zone"},
    {"log_level": "INVALID"},
])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_reason_is_kept_and_blank_clears_it(session):
    trip = add_trip(session, "phone:reason", datetime(2026, 9, 1, tzinfo=UTC))
    save_reason(session, trip.id, "  Défaut de vitesse  ")
    session.commit()
    assert trip.reason == "Défaut de vitesse"
    save_reason(session, trip.id, " \n ")
    session.commit()
    assert trip.reason is None


def test_reason_too_long_is_rejected(session):
    trip = add_trip(session, "phone:long", datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="trop long"):
        save_reason(session, trip.id, "a" * 2001)
    assert trip.reason is None


def test_marking_one_trip_does_not_draft_or_use_today_budget(session):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    first = add_trip(session, "phone:old", datetime(2026, 9, 1, tzinfo=UTC))
    second = add_trip(session, "phone:new", datetime(2026, 9, 2, tzinfo=UTC))
    mark_trip_handled(session, first.id)
    session.commit()
    assert first.claim.status == ClaimStatus.UNKNOWN
    assert first.claim.gmail_draft_id is None
    assert first.claim.sent_at is None
    assert [trip.id for trip in list_candidates(session)] == [second.id]
    assert remaining_draft_budget(session, Settings(), now) == 3


def test_perfect_score_cannot_be_marked_handled(session):
    trip = add_trip(session, "phone:perfect", datetime(2026, 9, 1, tzinfo=UTC), score=100)
    with pytest.raises(ValueError, match="pas à réclamer"):
        mark_trip_handled(session, trip.id)
    assert trip.claim is None


def test_claim_follow_up_stays_local(session):
    trip = add_trip(session, "phone:follow", datetime(2026, 9, 1, tzinfo=UTC))
    claim = Claim(trip_id=trip.id, status=ClaimStatus.DRAFT, gmail_draft_id="draft-1")
    session.add(claim)
    session.commit()
    update_claim(session, claim.id, "corrected", "Score revu")
    session.commit()
    assert claim.status == ClaimStatus.CORRECTED
    assert claim.response == "Score revu"
    assert claim.sent_at is None
    assert claim.gmail_draft_id == "draft-1"
    update_claim(session, claim.id, "pending", "  ")
    session.commit()
    assert claim.status == ClaimStatus.PENDING
    assert claim.response is None
    with pytest.raises(ValueError, match="Statut"):
        update_claim(session, claim.id, "sent", "note")
    assert claim.status == ClaimStatus.PENDING


def test_screen_preferences_roundtrip_without_dropping_other_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("YOUDRIVE_DB_PATH=data/youdrive.sqlite3\n", encoding="utf-8")
    save_preferences(env, "000", "Jérémie\nMobile", 3, "client.json")
    raw = env.read_text(encoding="utf-8")
    assert "YOUDRIVE_DB_PATH=data/youdrive.sqlite3" in raw
    assert "YOUDRIVE_MAIL_SIGNATURE" in raw
    before = dict(os.environ)
    try:
        for key in list(os.environ):
            if key.startswith("YOUDRIVE_"):
                del os.environ[key]
        settings = Settings.from_env(env)
        assert settings.contract_number == "000"
        assert settings.mail_signature == "Jérémie\nMobile"
        assert settings.daily_claim_limit == 3
        assert settings.gmail_client_file == Path("client.json")
    finally:
        os.environ.clear()
        os.environ.update(before)


def test_invalid_contract_is_not_written(tmp_path):
    env = tmp_path / ".env"
    env.write_text("YOUDRIVE_CONTRACT_NUMBER=000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalide"):
        save_preferences(env, "a b", "", 3, "")
    assert "a b" not in env.read_text(encoding="utf-8")


def test_process_environment_overrides_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("YOUDRIVE_DAILY_CLAIM_LIMIT=4\n", encoding="utf-8")
    monkeypatch.setenv("YOUDRIVE_DAILY_CLAIM_LIMIT", "2")
    monkeypatch.setenv("YOUDRIVE_DB_PATH", str(tmp_path / "settings.sqlite3"))
    assert Settings.from_env(env).daily_claim_limit == 2
    assert Settings.from_env(env).db_path == Path(tmp_path / "settings.sqlite3")
