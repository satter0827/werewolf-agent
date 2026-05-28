"""Add human player control state.

Revision ID: 0003_human_player_controls
Revises: 0002_run_summary_turns
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_human_player_controls"
down_revision = "0002_run_summary_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "game_runs",
        sa.Column("pending_actions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "game_runs",
        sa.Column(
            "control_token_hashes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("game_runs", "control_token_hashes")
    op.drop_column("game_runs", "pending_actions")
