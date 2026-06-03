"""Add manual player token state.

Revision ID: 0003_manual_player_tokens
Revises: 0002_game_summary_turns
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_manual_player_tokens"
down_revision = "0002_game_summary_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pending action and manual player token storage."""
    op.add_column(
        "games",
        sa.Column("pending_actions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "games",
        sa.Column(
            "manual_token_hashes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    """Drop pending action and manual player token storage."""
    op.drop_column("games", "manual_token_hashes")
    op.drop_column("games", "pending_actions")
