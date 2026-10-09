"""Turn the oldest trips scored below 100 into local claims after Gmail accepts."""

from datetime import datetime

from sqlalchemy.orm import Session

from youdrive.claims.errors import GmailError
from youdrive.claims.letters import build_message, require_contract
from youdrive.config import Settings
from youdrive.models import Claim, ClaimStatus
from youdrive.services.trips import list_candidates, remaining_draft_budget


def prepare_drafts(
    session: Session, settings: Settings, now: datetime, create, *,
    with_reason_only: bool = False, only_id: int | None = None,
) -> int:
    """Oldest candidates first. A saved reason is included; an empty one is not invented."""
    return _accept(
        session, settings, now, create, sent=False,
        with_reason_only=with_reason_only, only_id=only_id,
    )


def send_messages(
    session: Session, settings: Settings, now: datetime, send, *,
    with_reason_only: bool = False, only_id: int | None = None,
) -> int:
    """Same order and daily cap as drafts. Each accepted mail is recorded as sent."""
    return _accept(
        session, settings, now, send, sent=True,
        with_reason_only=with_reason_only, only_id=only_id,
    )


def _accept(
    session: Session, settings: Settings, now: datetime, deliver, *,
    sent: bool, with_reason_only: bool, only_id: int | None,
) -> int:
    require_contract(settings)
    budget = remaining_draft_budget(session, settings, now)
    chosen = list_candidates(session)
    if only_id is not None:
        chosen = [trip for trip in chosen if trip.id == only_id]
    if with_reason_only:
        chosen = [trip for trip in chosen if isinstance(trip.reason, str) and trip.reason.strip()]
    chosen = chosen[:budget]
    created = 0
    for trip in chosen:
        message, text = build_message(settings, trip)
        external_id = deliver(message)
        if not isinstance(external_id, str) or not external_id or len(external_id) > 256:
            raise GmailError("Envoi refusé." if sent else "Brouillon refusé.")
        session.add(Claim(
            trip_id=trip.id,
            created_at=now,
            status=ClaimStatus.PENDING if sent else ClaimStatus.DRAFT,
            text=text,
            gmail_draft_id=None if sent else external_id,
            sent_at=now if sent else None,
        ))
        session.commit()
        created += 1
    return created
