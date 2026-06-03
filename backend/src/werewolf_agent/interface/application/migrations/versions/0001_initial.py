"""Create game and event tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create base game and event tables."""
    op.create_table(
        "games",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("public_state", sa.JSON(), nullable=False),
        sa.Column("private_state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "game_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_id",
            sa.String(length=36),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("visibility", sa.String(length=24), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("day", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game_id", "sequence", name="game_events_game_sequence_unique"),
    )


def downgrade() -> None:
    """Drop base game and event tables."""
    op.drop_table("game_events")
    op.drop_table("games")
