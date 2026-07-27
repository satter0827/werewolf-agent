"""Application records for immutable user setup revisions."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.setup_document import GameSetupDocument


class SavedSetupSummary(ApplicationModel):
    """One user-owned setup with its current revision."""

    setup_id: str
    display_name: str
    latest_revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class SavedSetupRevision(ApplicationModel):
    """One immutable complete setup revision."""

    setup_id: str
    display_name: str
    revision: int = Field(ge=1)
    document: GameSetupDocument
    setup_checksum: str
    mechanics_checksum: str
    created_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = ["SavedSetupRevision", "SavedSetupSummary"]
