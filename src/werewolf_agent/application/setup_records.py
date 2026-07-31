"""Immutableなuser setup revisionのapplication記録を定義する."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.setup import GameSetupDocument


class SavedSetupSummary(ApplicationModel):
    """利用者が所有するsetupと現在のrevision概要を表す."""

    setup_id: str
    display_name: str
    latest_revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class SavedSetupRevision(ApplicationModel):
    """一つのimmutableな完全setup revisionを表す."""

    setup_id: str
    display_name: str
    revision: int = Field(ge=1)
    document: GameSetupDocument
    setup_checksum: str
    mechanics_checksum: str
    created_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = ["SavedSetupRevision", "SavedSetupSummary"]
