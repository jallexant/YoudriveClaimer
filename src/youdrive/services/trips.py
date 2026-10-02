from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from youdrive.config import Settings
from youdrive.models import Claim, ClaimStatus, Trip


def list_trips(session: Session) -> list[Trip]:
    return list(session.scalars(select(Trip).order_by(Trip.started_at, Trip.id)))


def list_candidates(session: Session) -> list[Trip]:
    statement = select(Trip).where(Trip.score < 100, ~Trip.claim.has())
    return list(session.scalars(statement.order_by(Trip.started_at, Trip.id)))


def count_sent_today(session: Session, now: datetime, timezone: str) -> int:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Une date doit inclure son fuseau horaire.")
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    start = datetime.combine(today, time.min, zone).astimezone(UTC)
    end = datetime.combine(today + timedelta(days=1), time.min, zone).astimezone(UTC)
    return session.scalar(
        select(func.count(Claim.id)).where(Claim.sent_at >= start, Claim.sent_at < end)
    ) or 0


def remaining_daily_budget(session: Session, settings: Settings, now: datetime) -> int:
    return max(0, settings.daily_claim_limit - count_sent_today(session, now, settings.timezone))


@dataclass(frozen=True)
class Summary:
    trips: int
    low_scores: int
    candidates: int
    claims: int
    statuses: dict[str, int]


def summarize(session: Session) -> Summary:
    counts = dict(session.execute(select(Claim.status, func.count()).group_by(Claim.status)).all())
    return Summary(
        trips=session.scalar(select(func.count(Trip.id))) or 0,
        low_scores=session.scalar(select(func.count(Trip.id)).where(Trip.score < 100)) or 0,
        candidates=session.scalar(
            select(func.count(Trip.id)).where(Trip.score < 100, ~Trip.claim.has())
        ) or 0,
        claims=sum(counts.values()),
        statuses={status.value: counts.get(status, 0) for status in ClaimStatus},
    )
