"""Add manual player token state.

Revision ID: 0003_manual_player_tokens
Revises: 0002_game_summary_turns
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from werewolf_agent.interface.application import schema

revision = "0003_manual_player_tokens"
down_revision = "0002_game_summary_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pending action and manual player token storage."""
    op.add_column(
        schema.GAMES_TABLE,
        sa.Column(
            schema.PENDING_ACTIONS_COLUMN,
            sa.JSON(),
            nullable=False,
            server_default=sa.text(schema.EMPTY_JSON_OBJECT_SQL),
        ),
    )
    op.add_column(
        schema.GAMES_TABLE,
        sa.Column(
            schema.MANUAL_TOKEN_HASHES_COLUMN,
            sa.JSON(),
            nullable=False,
            server_default=sa.text(schema.EMPTY_JSON_OBJECT_SQL),
        ),
    )


def downgrade() -> None:
    """Drop pending action and manual player token storage."""
    op.drop_column(schema.GAMES_TABLE, schema.MANUAL_TOKEN_HASHES_COLUMN)
    op.drop_column(schema.GAMES_TABLE, schema.PENDING_ACTIONS_COLUMN)
