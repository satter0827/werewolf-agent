"""Create game and event tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from werewolf_agent.interface.application import schema

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create base game and event tables."""
    op.create_table(
        schema.GAMES_TABLE,
        sa.Column(schema.ID_COLUMN, sa.String(length=schema.UUID_TEXT_LENGTH), primary_key=True),
        sa.Column(
            schema.STATUS_COLUMN, sa.String(length=schema.STATUS_TEXT_LENGTH), nullable=False
        ),
        sa.Column(schema.PHASE_COLUMN, sa.String(length=schema.PHASE_TEXT_LENGTH), nullable=False),
        sa.Column(schema.DAY_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.SEED_COLUMN, sa.Integer(), nullable=True),
        sa.Column(schema.CONFIG_COLUMN, sa.JSON(), nullable=False),
        sa.Column(schema.PUBLIC_STATE_COLUMN, sa.JSON(), nullable=False),
        sa.Column(schema.PRIVATE_STATE_COLUMN, sa.JSON(), nullable=False),
        sa.Column(schema.VERSION_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.CREATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
        sa.Column(schema.UPDATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        schema.GAME_EVENTS_TABLE,
        sa.Column(schema.ID_COLUMN, sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            schema.GAME_ID_COLUMN,
            sa.String(length=schema.UUID_TEXT_LENGTH),
            sa.ForeignKey(schema.GAMES_ID_REFERENCE, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(schema.SEQUENCE_COLUMN, sa.Integer(), nullable=False),
        sa.Column(
            schema.EVENT_ID_COLUMN, sa.String(length=schema.UUID_TEXT_LENGTH), nullable=False
        ),
        sa.Column(
            schema.VISIBILITY_COLUMN,
            sa.String(length=schema.STATUS_TEXT_LENGTH),
            nullable=False,
        ),
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
        sa.UniqueConstraint(
            schema.GAME_ID_COLUMN,
            schema.SEQUENCE_COLUMN,
            name=schema.GAME_EVENTS_GAME_SEQUENCE_UNIQUE,
        ),
    )


def downgrade() -> None:
    """Drop base game and event tables."""
    op.drop_table(schema.GAME_EVENTS_TABLE)
    op.drop_table(schema.GAMES_TABLE)
