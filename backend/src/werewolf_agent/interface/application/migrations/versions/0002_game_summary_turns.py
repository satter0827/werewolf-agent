"""Add game summary and turn read models.

Revision ID: 0002_game_summary_turns
Revises: 0001_initial
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from werewolf_agent.interface.application import schema

revision = "0002_game_summary_turns"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create public game summary and timeline read model tables."""
    op.create_table(
        schema.GAME_SUMMARIES_TABLE,
        sa.Column(schema.GAME_ID_COLUMN, sa.String(length=schema.UUID_TEXT_LENGTH), nullable=False),
        sa.Column(
            schema.STATUS_COLUMN, sa.String(length=schema.STATUS_TEXT_LENGTH), nullable=False
        ),
        sa.Column(schema.PHASE_COLUMN, sa.String(length=schema.PHASE_TEXT_LENGTH), nullable=False),
        sa.Column(schema.DAY_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.VERSION_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.SEED_COLUMN, sa.Integer(), nullable=True),
        sa.Column(schema.PLAYER_COUNT_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.ALIVE_COUNT_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.WINNER_COLUMN, sa.String(length=schema.WINNER_TEXT_LENGTH), nullable=True),
        sa.Column(schema.STEP_COUNT_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.TURN_COUNT_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.CREATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
        sa.Column(schema.UPDATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
        sa.Column(schema.COMPLETED_AT_COLUMN, sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            [schema.GAME_ID_COLUMN],
            [schema.GAMES_ID_REFERENCE],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(schema.GAME_ID_COLUMN),
    )
    op.create_table(
        schema.GAME_TURNS_TABLE,
        sa.Column(schema.ID_COLUMN, sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(schema.GAME_ID_COLUMN, sa.String(length=schema.UUID_TEXT_LENGTH), nullable=False),
        sa.Column(schema.SEQUENCE_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.EVENT_SEQUENCE_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.VERSION_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.PHASE_COLUMN, sa.String(length=schema.PHASE_TEXT_LENGTH), nullable=True),
        sa.Column(schema.DAY_COLUMN, sa.Integer(), nullable=True),
        sa.Column(
            schema.ACTOR_ID_COLUMN, sa.String(length=schema.ACTOR_ID_TEXT_LENGTH), nullable=True
        ),
        sa.Column(
            schema.EVENT_TYPE_COLUMN,
            sa.String(length=schema.EVENT_TYPE_TEXT_LENGTH),
            nullable=False,
        ),
        sa.Column(schema.PAYLOAD_COLUMN, sa.JSON(), nullable=False),
        sa.Column(schema.OCCURRED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            [schema.GAME_ID_COLUMN],
            [schema.GAMES_ID_REFERENCE],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            schema.GAME_ID_COLUMN,
            schema.SEQUENCE_COLUMN,
            name=schema.GAME_TURNS_GAME_SEQUENCE_UNIQUE,
        ),
        sa.UniqueConstraint(
            schema.GAME_ID_COLUMN,
            schema.EVENT_SEQUENCE_COLUMN,
            name=schema.GAME_TURNS_GAME_EVENT_UNIQUE,
        ),
    )


def downgrade() -> None:
    """Drop public game summary and timeline read model tables."""
    op.drop_table(schema.GAME_TURNS_TABLE)
    op.drop_table(schema.GAME_SUMMARIES_TABLE)
