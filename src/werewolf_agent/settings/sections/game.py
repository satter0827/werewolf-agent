"""game runtime settings section."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_PLAYER_COUNT,
)
from werewolf_agent.settings.constants import (
    NarrationMode as SharedNarrationMode,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_GAME_ABILITIES_FILE,
    DEFAULT_GAME_CATALOG_FILE,
    DEFAULT_GAME_DEFAULT_NARRATION_MODE,
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_DEFAULT_SETUP_PRESET_ID,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_GAME_PHASE_NAMES,
    DEFAULT_GAME_ROLE_NAMES,
    DEFAULT_GAME_ROLES_FILE,
    DEFAULT_GAME_RULES_FILE,
    DEFAULT_GAME_SETUP_DESCRIPTION_TEMPLATE,
    DEFAULT_GAME_SUPPORTED_AGENT_NAME,
    DEFAULT_GAME_SUPPORTED_AGENT_TYPE,
)


class GameSettings(BaseModel):
    """Settings owned by the game runtime boundary."""

    game_min_players: int = Field(
        default=DEFAULT_GAME_MIN_PLAYERS,
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_MIN_PLAYERS",
    )
    game_max_players: int = Field(
        default=DEFAULT_GAME_MAX_PLAYERS,
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_MAX_PLAYERS",
    )
    game_default_player_count: int = Field(
        default=DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
        ge=MIN_PLAYER_COUNT,
        validation_alias="WEREWOLF_GAME_DEFAULT_PLAYER_COUNT",
    )
    game_supported_agent_type: str = Field(
        default=DEFAULT_GAME_SUPPORTED_AGENT_TYPE,
        validation_alias="WEREWOLF_GAME_SUPPORTED_AGENT_TYPE",
    )
    game_supported_agent_name: str = Field(
        default=DEFAULT_GAME_SUPPORTED_AGENT_NAME,
        validation_alias="WEREWOLF_GAME_SUPPORTED_AGENT_NAME",
    )
    game_default_narration_mode: SharedNarrationMode = Field(
        default=cast(SharedNarrationMode, DEFAULT_GAME_DEFAULT_NARRATION_MODE),
        validation_alias="WEREWOLF_GAME_DEFAULT_NARRATION_MODE",
    )
    game_default_setup_preset_id: str = Field(
        default=DEFAULT_GAME_DEFAULT_SETUP_PRESET_ID,
        validation_alias="WEREWOLF_GAME_DEFAULT_SETUP_PRESET_ID",
    )
    game_rules_file: str = Field(
        default=DEFAULT_GAME_RULES_FILE,
        validation_alias="WEREWOLF_GAME_RULES_FILE",
    )
    game_roles_file: str = Field(
        default=DEFAULT_GAME_ROLES_FILE,
        validation_alias="WEREWOLF_GAME_ROLES_FILE",
    )
    game_catalog_file: str = Field(
        default=DEFAULT_GAME_CATALOG_FILE,
        validation_alias="WEREWOLF_GAME_CATALOG_FILE",
    )
    game_abilities_file: str = Field(
        default=DEFAULT_GAME_ABILITIES_FILE,
        validation_alias="WEREWOLF_GAME_ABILITIES_FILE",
    )
    game_setup_description_template: str = Field(
        default=DEFAULT_GAME_SETUP_DESCRIPTION_TEMPLATE,
        validation_alias="WEREWOLF_GAME_SETUP_DESCRIPTION_TEMPLATE",
    )
    game_role_names: str = Field(
        default=DEFAULT_GAME_ROLE_NAMES,
        validation_alias="WEREWOLF_GAME_ROLE_NAMES",
    )
    game_phase_names: str = Field(
        default=DEFAULT_GAME_PHASE_NAMES,
        validation_alias="WEREWOLF_GAME_PHASE_NAMES",
    )
