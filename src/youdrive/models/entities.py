from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite stores naive UTC; application code always receives aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Une date doit inclure son fuseau horaire.")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="valid_score"),
        CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="valid_distance"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="valid_duration"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="valid_trip_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    youdrive_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    score: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    gps: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claim: Mapped["Claim | None"] = relationship(back_populates="trip", uselist=False)


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    status: Mapped[ClaimStatus] = mapped_column(
        SqlEnum(
            ClaimStatus, values_callable=lambda cls: [item.value for item in cls],
            native_enum=False, create_constraint=True, validate_strings=True,
        ), default=ClaimStatus.DRAFT,
    )
    text: Mapped[str | None] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    gmail_draft_id: Mapped[str | None] = mapped_column(String)
    trip: Mapped[Trip] = relationship(back_populates="claim")
