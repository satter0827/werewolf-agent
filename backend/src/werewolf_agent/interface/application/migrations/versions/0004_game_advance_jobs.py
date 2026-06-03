"""Add game advance jobs.

Revision ID: 0004_game_advance_jobs
Revises: 0003_manual_player_tokens
Create Date: 2026-06-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from werewolf_agent.interface.application import schema

revision = "0004_game_advance_jobs"
down_revision = "0003_manual_player_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create API-side advance job storage."""
    op.create_table(
        schema.GAME_ADVANCE_JOBS_TABLE,
        sa.Column(schema.ID_COLUMN, sa.String(schema.UUID_TEXT_LENGTH), primary_key=True),
        sa.Column(
            schema.GAME_ID_COLUMN,
            sa.String(schema.UUID_TEXT_LENGTH),
            sa.ForeignKey(schema.GAMES_ID_REFERENCE, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(schema.STATUS_COLUMN, sa.String(schema.STATUS_TEXT_LENGTH), nullable=False),
        sa.Column(schema.STATE_VERSION_COLUMN, sa.Integer(), nullable=False),
        sa.Column(schema.RESULT_COLUMN, sa.JSON(), nullable=True),
        sa.Column(schema.ERROR_COLUMN, sa.JSON(), nullable=True),
        sa.Column(schema.CREATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
        sa.Column(schema.STARTED_AT_COLUMN, sa.DateTime(timezone=True), nullable=True),
        sa.Column(schema.COMPLETED_AT_COLUMN, sa.DateTime(timezone=True), nullable=True),
        sa.Column(schema.UPDATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop API-side advance job storage."""
    op.drop_table(schema.GAME_ADVANCE_JOBS_TABLE)
