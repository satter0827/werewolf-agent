"""SQLAlchemy persistence models for game runs and events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class GameRunModel(Base):
    """Persisted game run owned by the API server."""

    __tablename__ = "game_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    public_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    private_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list[GameEventModel]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class GameEventModel(Base):
    """Persisted event stream record for one game run."""

    __tablename__ = "game_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="game_events_run_sequence_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("game_runs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    visibility: Mapped[str] = mapped_column(String(24), nullable=False, default="public")
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[GameRunModel] = relationship(back_populates="events")


def max_event_sequence() -> Any:
    """Return the aggregate expression for the last event sequence."""
    return func.max(GameEventModel.sequence)
