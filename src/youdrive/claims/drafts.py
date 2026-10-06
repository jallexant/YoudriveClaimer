"""Turn the oldest trips scored below 100 into local claims after Gmail accepts."""

from datetime import datetime

from sqlalchemy.orm import Session

from youdrive.claims.letters import build_message, require_contract
from youdrive.config import Settings
from youdrive.models import Claim, ClaimStatus
from youdrive.services.trips import list_candidates, remaining_draft_budget


def prepare_drafts(session: Session, settings: Settings, now: datetime, create) -> int:
    require_contract(settings)
    budget = remaining_draft_budget(session, settings, now)
    chosen = list_candidates(session)[:budget]
    created = 0
    for trip in chosen:
        message, text = build_message(settings, trip)
        draft_id = create(message)
        session.add(Claim(
            trip_id=trip.id, status=ClaimStatus.DRAFT, text=text, gmail_draft_id=draft_id,
        ))
        session.commit()
        created += 1
    return created
