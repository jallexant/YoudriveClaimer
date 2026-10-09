"""Local operations behind the screen. Nothing is sent."""

import threading
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, date, datetime, time
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import select

from youdrive.claims.drafts import prepare_drafts, send_messages
from youdrive.claims.errors import GmailError
from youdrive.claims.gmail import create_draft, login, needs_reconnect, send_message, token_path
from youdrive.claims.letters import require_contract, screenshot_path
from youdrive.config import Settings, save_preferences
from youdrive.db.session import initialize_database, open_database
from youdrive.models import Claim, ClaimStatus, Trip
from youdrive.phone.adb import Adb
from youdrive.phone.collect import collect_trips
from youdrive.phone.errors import PhoneError
from youdrive.services.sync import import_phone_trips
from youdrive.services.trips import (
    list_trips,
    mark_claimed_before,
    mark_trip_handled,
    remaining_draft_budget,
    save_reason,
)
from youdrive.ui.present import Snapshot, TripCard, route_labels

_lock = threading.Lock()


def current_settings() -> Settings:
    load_dotenv(Path(".env"), override=True)
    return Settings.from_env()


@contextmanager
def session_scope(settings: Settings | None = None):
    settings = current_settings() if settings is None else settings
    with _lock:
        engine, sessions = open_database(settings.db_path)
        initialize_database(engine)
        try:
            with sessions() as session:
                yield settings, session
        finally:
            engine.dispose()


def phone_status() -> str | None:
    try:
        Adb().ensure_device()
    except PhoneError as exc:
        return str(exc)
    return None


def load_snapshot() -> Snapshot:
    with session_scope() as (settings, session):
        cards = tuple(_card(settings, trip) for trip in list_trips(session))
        budget = remaining_draft_budget(session, settings, datetime.now(UTC))
        reconnect = needs_reconnect(settings)
        return Snapshot(
            timezone=settings.timezone,
            daily_limit=settings.daily_claim_limit,
            budget_left=budget,
            contract_ok=_contract_ok(settings),
            gmail_ok=token_path(settings).is_file() and not reconnect,
            gmail_reconnect=reconnect,
            default_message=bool(settings.default_claim_message.strip()),
            trips=cards,
        )


def remember_reason(trip_id: int, reason: str) -> None:
    with session_scope() as (_settings, session):
        save_reason(session, trip_id, reason)
        session.commit()


def handle_trip(trip_id: int) -> None:
    with session_scope() as (_settings, session):
        mark_trip_handled(session, trip_id)
        session.commit()


def mark_before(raw_day: str) -> int:
    try:
        day = date.fromisoformat(raw_day)
    except ValueError as exc:
        raise ValueError("Choisissez une date.") from exc
    with session_scope() as (settings, session):
        cutoff = datetime.combine(day, time.min, ZoneInfo(settings.timezone))
        marked = mark_claimed_before(session, cutoff)
        session.commit()
        return marked


def create_ready_drafts() -> tuple[int, int, int]:
    return _deliver(None, send=False)


def create_one_draft(trip_id: int) -> tuple[int, int, int]:
    return _deliver(trip_id, send=False)


def send_ready_messages() -> tuple[int, int, int]:
    return _deliver(None, send=True)


def send_one_message(trip_id: int) -> tuple[int, int, int]:
    return _deliver(trip_id, send=True)


def _deliver(only_id: int | None, *, send: bool) -> tuple[int, int, int]:
    settings = current_settings()
    with session_scope(settings) as (_settings, session):
        now = datetime.now(UTC)
        if only_id is not None and remaining_draft_budget(session, settings, now) < 1:
            raise ValueError("Le plafond du jour est atteint.")
        if send:
            made = send_messages(
                session, settings, now,
                lambda message: send_message(settings, message),
                with_reason_only=True,
                only_id=only_id,
            )
        else:
            made = prepare_drafts(
                session, settings, now,
                lambda message: create_draft(settings, message),
                with_reason_only=True,
                only_id=only_id,
            )
        if only_id is not None and made == 0:
            raise ValueError("Écrivez le motif, ou ce trajet n'est plus à préparer.")
        left = remaining_draft_budget(session, settings, now)
    return made, left, settings.daily_claim_limit


def sync_phone(
    full: bool, on_progress: Callable[[str], None],
) -> tuple[int, int, int, int, bool]:
    settings = current_settings()
    known: set[str] = set()
    if not full:
        with session_scope(settings) as (_settings, session):
            known = set(session.scalars(
                select(Trip.youdrive_id).where(Trip.youdrive_id.like("phone:%"))
            ))
    incoming, reached = collect_trips(
        Adb(), settings.timezone, sleep,
        settings.db_path.parent / "screenshots", known, on_progress=on_progress,
    )
    on_progress("Enregistrement des trajets sur cet ordinateur.")
    with session_scope(settings) as (_settings, session):
        added, updated = import_phone_trips(session, incoming)
        session.commit()
    shots = sum(trip.screenshot_name is not None for trip in incoming)
    return len(incoming), added, updated, shots, reached


def connect_gmail(on_url: Callable[[str], None] | None = None) -> None:
    login(current_settings(), on_url=on_url)


def write_preferences(
    contract: str, signature: str, daily_limit: int, client: str, attach_screenshot: bool,
    default_message: str = "",
) -> None:
    save_preferences(
        Path(".env"), contract, signature, daily_limit, client, attach_screenshot,
        default_message,
    )


def _contract_ok(settings: Settings) -> bool:
    try:
        require_contract(settings)
    except GmailError:
        return False
    return True


def _claim_at(claim: Claim | None) -> datetime | None:
    if claim is None or claim.status is ClaimStatus.UNKNOWN:
        return None
    return claim.sent_at or claim.created_at


def _card(settings: Settings, trip: Trip) -> TripCard:
    start, end = route_labels(trip.gps)
    shot = screenshot_path(settings, trip)
    claim = trip.claim
    return TripCard(
        id=trip.id,
        started_at=trip.started_at,
        score=trip.score,
        distance_km=trip.distance_km,
        duration_seconds=trip.duration_seconds,
        start_label=start,
        end_label=end,
        reason=trip.reason or "",
        screenshot=shot.name if shot is not None else None,
        claim_id=None if claim is None else claim.id,
        claim_status=None if claim is None else claim.status.value,
        claim_at=_claim_at(claim),
        claim_text="" if claim is None else (claim.text or ""),
    )
