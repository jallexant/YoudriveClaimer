from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from youdrive.models import Trip
from youdrive.phone.errors import PhoneError
from youdrive.phone.screen import PhoneTrip


def import_phone_trips(session: Session, trips: list[PhoneTrip]) -> tuple[int, int]:
    """Caller commits the batch. Existing rows and claims stay attached."""
    identities = [incoming.remote_id for incoming in trips]
    if len(identities) != len(set(identities)):
        raise PhoneError("Identité de trajet dupliquée ; aucun import effectué.")
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
        previous = trip.gps if isinstance(trip.gps, dict) else {}
        screenshot = incoming.screenshot_name or previous.get("screenshot")
        gps = {"start_label": incoming.start_label, "end_label": incoming.end_label}
        if isinstance(screenshot, str):
            gps["screenshot"] = screenshot
        trip.events = []
        trip.gps = gps
        trip.last_synced_at = now
    session.flush()
    return added, updated
