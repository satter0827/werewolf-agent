"""SQLAlchemy persistence models for games and events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from werewolf_agent.interface.application import schema


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class GameModel(Base):
    """Persisted game owned by the API server."""

    __tablename__ = schema.GAMES_TABLE

    id: Mapped[str] = mapped_column(String(schema.UUID_TEXT_LENGTH), primary_key=True)
    status: Mapped[str] = mapped_column(String(schema.STATUS_TEXT_LENGTH), nullable=False)
    phase: Mapped[str] = mapped_column(String(schema.PHASE_TEXT_LENGTH), nullable=False)
    day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=schema.INITIAL_GAME_DAY,
    )
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    public_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    private_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pending_actions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manual_token_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=schema.INITIAL_GAME_VERSION,
    )
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
    advance_jobs: Mapped[list[GameAdvanceJobModel]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class GameAdvanceJobModel(Base):
    """Persisted API-side advance job for one game."""

    __tablename__ = schema.GAME_ADVANCE_JOBS_TABLE

    id: Mapped[str] = mapped_column(String(schema.UUID_TEXT_LENGTH), primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey(schema.GAMES_ID_REFERENCE, ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(schema.STATUS_TEXT_LENGTH), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped[GameModel] = relationship(back_populates="advance_jobs")


class GameEventModel(Base):
    """Persisted event stream record for one game."""

    __tablename__ = schema.GAME_EVENTS_TABLE
    __table_args__ = (
        UniqueConstraint(
            schema.GAME_ID_COLUMN,
            schema.SEQUENCE_COLUMN,
            name=schema.GAME_EVENTS_GAME_SEQUENCE_UNIQUE,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey(schema.GAMES_ID_REFERENCE, ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(
        String(schema.UUID_TEXT_LENGTH),
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    visibility: Mapped[str] = mapped_column(
        String(schema.STATUS_TEXT_LENGTH),
        nullable=False,
        default=schema.DEFAULT_EVENT_VISIBILITY,
    )
    phase: Mapped[str | None] = mapped_column(String(schema.PHASE_TEXT_LENGTH), nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(
        String(schema.ACTOR_ID_TEXT_LENGTH),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(schema.EVENT_TYPE_TEXT_LENGTH), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped[GameModel] = relationship(back_populates="events")


class GameSummaryModel(Base):
    """Persisted read model for game lists and analytics."""

    __tablename__ = schema.GAME_SUMMARIES_TABLE

    game_id: Mapped[str] = mapped_column(
        ForeignKey(schema.GAMES_ID_REFERENCE, ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(schema.STATUS_TEXT_LENGTH), nullable=False)
    phase: Mapped[str] = mapped_column(String(schema.PHASE_TEXT_LENGTH), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player_count: Mapped[int] = mapped_column(Integer, nullable=False)
    alive_count: Mapped[int] = mapped_column(Integer, nullable=False)
    winner: Mapped[str | None] = mapped_column(String(schema.WINNER_TEXT_LENGTH), nullable=True)
    step_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=schema.EMPTY_COUNT_DEFAULT,
    )
    turn_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=schema.EMPTY_COUNT_DEFAULT,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped[GameModel] = relationship(back_populates="summary")


class GameTurnModel(Base):
    """Persisted public timeline read model for one game."""

    __tablename__ = schema.GAME_TURNS_TABLE
    __table_args__ = (
        UniqueConstraint(
            schema.GAME_ID_COLUMN,
            schema.SEQUENCE_COLUMN,
            name=schema.GAME_TURNS_GAME_SEQUENCE_UNIQUE,
        ),
        UniqueConstraint(
            schema.GAME_ID_COLUMN,
            schema.EVENT_SEQUENCE_COLUMN,
            name=schema.GAME_TURNS_GAME_EVENT_UNIQUE,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey(schema.GAMES_ID_REFERENCE, ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str | None] = mapped_column(String(schema.PHASE_TEXT_LENGTH), nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(
        String(schema.ACTOR_ID_TEXT_LENGTH),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(schema.EVENT_TYPE_TEXT_LENGTH), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    game: Mapped[GameModel] = relationship(back_populates="turns")


def max_event_sequence() -> Any:
    """Return the aggregate expression for the last event sequence."""
    return func.max(GameEventModel.sequence)


def max_turn_sequence() -> Any:
    """Return the aggregate expression for the last turn sequence."""
    return func.max(GameTurnModel.sequence)
