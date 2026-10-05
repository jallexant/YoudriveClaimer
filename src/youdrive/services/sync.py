from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from youdrive.api.android import AndroidError, AndroidTrip
from youdrive.api.web import WebTrip
from youdrive.models import Trip


def import_web_trips(session: Session, trips: list[WebTrip]) -> tuple[int, int]:
    """Caller commits the batch; absent trips and unavailable details stay intact."""
    added = updated = 0
    now = datetime.now(UTC)
    for incoming in trips:
        trip = session.scalar(select(Trip).where(Trip.youdrive_id == incoming.remote_id))
        if trip is None:
            trip = Trip(youdrive_id=incoming.remote_id, imported_at=now)
            session.add(trip)
            added += 1
        else:
            updated += 1
        trip.started_at = incoming.started_at
        trip.ended_at = incoming.ended_at
        trip.score = incoming.score
        trip.distance_km = incoming.distance_km
        trip.duration_seconds = incoming.duration_seconds
        trip.last_synced_at = now
    session.flush()
    return added, updated


def import_android_trips(session: Session, trips: list[AndroidTrip]) -> tuple[int, int]:
    """Caller commits the batch. Existing web rows and claims stay attached."""
    identities = [incoming.remote_id for incoming in trips]
    if len(identities) != len(set(identities)):
        raise AndroidError("Identité de trajet dupliquée ; aucun import effectué.")
    added = updated = 0
    now = datetime.now(UTC)
    for incoming in trips:
        trip = session.scalar(select(Trip).where(Trip.youdrive_id == incoming.remote_id))
        if trip is None:
            trip = Trip(youdrive_id=incoming.remote_id, imported_at=now)
            session.add(trip)
            added += 1
        else:
            updated += 1
        trip.started_at = incoming.started_at
        trip.ended_at = incoming.ended_at
        trip.score = incoming.score
        trip.distance_km = incoming.distance_km
        trip.duration_seconds = incoming.duration_seconds
        trip.events = incoming.events
        trip.gps = incoming.gps
        trip.last_synced_at = now
    session.flush()
    return added, updated
