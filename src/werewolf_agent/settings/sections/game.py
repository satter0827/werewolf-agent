"""game runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_PLAYER_COUNT,
)


class GameSettings(BaseModel):
    """Settings owned by the game runtime boundary."""

    game_min_players: int = Field(
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_MIN_PLAYERS",
    )
    game_max_players: int = Field(
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_MAX_PLAYERS",
    )
    game_supported_agent_name: str = Field(
        validation_alias="WEREWOLF_GAME_SUPPORTED_AGENT_NAME",
    )
