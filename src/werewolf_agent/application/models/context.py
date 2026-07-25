"""Immutable context for application operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from werewolf_agent.application.constants import (
    MIN_PAGE_LIMIT,
    NARRATION_MODE_CHOICES,
    NarrationMode,
)
from werewolf_agent.application.definitions import (
    GameDefinitions,
    PlayerSetupDefinitions,
)
from werewolf_agent.application.messages import (
    MESSAGE_DEFAULT_NARRATION_MODE_UNSUPPORTED,
    MESSAGE_DEFAULT_PLAYER_COUNT_WITHIN_MIN_MAX,
    MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE,
    MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX,
    MESSAGE_GAME_LIST_MAX_LIMIT_MUST_BE_AT_LEAST_ONE,
    MESSAGE_MAX_PLAYERS_MUST_BE_GE_MIN_PLAYERS,
    MESSAGE_MIN_PLAYERS_MUST_BE_AT_LEAST_ONE,
    MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE,
    MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX,
    MESSAGE_TIMELINE_MAX_LIMIT_MUST_BE_AT_LEAST_ONE,
)
from werewolf_agent.contracts.validation import non_blank

if TYPE_CHECKING:
    from werewolf_agent.application.ports import GameRepository

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


@dataclass(frozen=True)
class GameApplicationConfig:
    """Business settings used by stateless game jobs."""

    min_players: int
    max_players: int
    default_player_count: int
    supported_agent_type: str
    default_setup_preset_id: str
    default_agent_strategy_id: str
    default_narration_mode: NarrationMode
    game_list_default_limit: int
    game_list_max_limit: int
    timeline_default_limit: int
    timeline_max_limit: int

    def __post_init__(self) -> None:
        """Validate business settings supplied by the outer layer."""
        if self.min_players < 1:
            raise ValueError(MESSAGE_MIN_PLAYERS_MUST_BE_AT_LEAST_ONE)
        if self.max_players < self.min_players:
            raise ValueError(MESSAGE_MAX_PLAYERS_MUST_BE_GE_MIN_PLAYERS)
        if not self.min_players <= self.default_player_count <= self.max_players:
            raise ValueError(MESSAGE_DEFAULT_PLAYER_COUNT_WITHIN_MIN_MAX)
        if self.default_narration_mode not in NARRATION_MODE_CHOICES:
            raise ValueError(MESSAGE_DEFAULT_NARRATION_MODE_UNSUPPORTED)
        object.__setattr__(
            self,
            "default_agent_strategy_id",
            non_blank(self.default_agent_strategy_id, "default_agent_strategy_id"),
        )
        object.__setattr__(
            self,
            "default_setup_preset_id",
            non_blank(self.default_setup_preset_id, "default_setup_preset_id"),
        )
        if self.game_list_default_limit < MIN_PAGE_LIMIT:
            raise ValueError(MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE)
        if self.game_list_max_limit < MIN_PAGE_LIMIT:
            raise ValueError(MESSAGE_GAME_LIST_MAX_LIMIT_MUST_BE_AT_LEAST_ONE)
        if self.game_list_default_limit > self.game_list_max_limit:
            raise ValueError(MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX)
        if self.timeline_default_limit < MIN_PAGE_LIMIT:
            raise ValueError(MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE)
        if self.timeline_max_limit < MIN_PAGE_LIMIT:
            raise ValueError(MESSAGE_TIMELINE_MAX_LIMIT_MUST_BE_AT_LEAST_ONE)
        if self.timeline_default_limit > self.timeline_max_limit:
            raise ValueError(MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX)


@dataclass(frozen=True)
class ApplicationContext:
    """Externally supplied dependencies for game operations."""

    repository: GameRepository
    game_definitions: GameDefinitions
    player_definitions: PlayerSetupDefinitions
    config: GameApplicationConfig
    create_llm_mode: Literal["fake", "paid"] = "fake"
