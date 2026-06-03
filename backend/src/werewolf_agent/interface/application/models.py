"""SQLAlchemy persistence models for games and events."""

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


class GameModel(Base):
    """Persisted game owned by the API server."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    public_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    private_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pending_actions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manual_token_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list[GameEventModel]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    summary: Mapped[GameSummaryModel | None] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    turns: Mapped[list[GameTurnModel]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class GameEventModel(Base):
    """Persisted event stream record for one game."""

    __tablename__ = "game_events"
    __table_args__ = (
        UniqueConstraint("game_id", "sequence", name="game_events_game_sequence_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
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

    game: Mapped[GameModel] = relationship(back_populates="events")


class GameSummaryModel(Base):
    """Persisted read model for game lists and analytics."""

    __tablename__ = "game_summaries"

    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player_count: Mapped[int] = mapped_column(Integer, nullable=False)
    alive_count: Mapped[int] = mapped_column(Integer, nullable=False)
    winner: Mapped[str | None] = mapped_column(String(24), nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped[GameModel] = relationship(back_populates="summary")


class GameTurnModel(Base):
    """Persisted public timeline read model for one game."""

    __tablename__ = "game_turns"
    __table_args__ = (
        UniqueConstraint("game_id", "sequence", name="game_turns_game_sequence_unique"),
        UniqueConstraint("game_id", "event_sequence", name="game_turns_game_event_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped[GameModel] = relationship(back_populates="turns")


def max_event_sequence() -> Any:
    """Return the aggregate expression for the last event sequence."""
    return func.max(GameEventModel.sequence)


def max_turn_sequence() -> Any:
    """Return the aggregate expression for the last turn sequence."""
    return func.max(GameTurnModel.sequence)
