"""Add run summary and turn read models.

Revision ID: 0002_run_summary_turns
Revises: 0001_initial
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_run_summary_turns"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create public run summary and timeline read model tables."""
    op.create_table(
        "game_run_summaries",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("alive_count", sa.Integer(), nullable=False),
        sa.Column("winner", sa.String(length=24), nullable=True),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["game_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "game_turns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("day", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["game_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence", name="game_turns_run_sequence_unique"),
        sa.UniqueConstraint("run_id", "event_sequence", name="game_turns_run_event_unique"),
    )


def downgrade() -> None:
    """Drop public run summary and timeline read model tables."""
    op.drop_table("game_turns")
    op.drop_table("game_run_summaries")
