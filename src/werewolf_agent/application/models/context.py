"""Application operationへ渡すimmutable contextを定義する."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from werewolf_agent.application.constants import MIN_PAGE_LIMIT
from werewolf_agent.application.messages import (
    MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE,
    MESSAGE_GAME_LIST_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX,
    MESSAGE_GAME_LIST_MAX_LIMIT_MUST_BE_AT_LEAST_ONE,
    MESSAGE_MAX_PLAYERS_MUST_BE_GE_MIN_PLAYERS,
    MESSAGE_MIN_PLAYERS_MUST_BE_AT_LEAST_ONE,
    MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_BE_AT_LEAST_ONE,
    MESSAGE_TIMELINE_DEFAULT_LIMIT_MUST_NOT_EXCEED_MAX,
    MESSAGE_TIMELINE_MAX_LIMIT_MUST_BE_AT_LEAST_ONE,
)
from werewolf_agent.application.rule_packs import RulePackRegistry

if TYPE_CHECKING:
    from werewolf_agent.application.ports import GameRepository

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


@dataclass(frozen=True)
class GameApplicationConfig:
    """Statelessなゲーム処理が使用するbusiness設定を表す."""

    min_players: int
    max_players: int
    game_list_default_limit: int
    game_list_max_limit: int
    timeline_default_limit: int
    timeline_max_limit: int

    def __post_init__(self) -> None:
        """外側のlayerから渡されたbusiness設定を検証する."""
        if self.min_players < 1:
            raise ValueError(MESSAGE_MIN_PLAYERS_MUST_BE_AT_LEAST_ONE)
        if self.max_players < self.min_players:
            raise ValueError(MESSAGE_MAX_PLAYERS_MUST_BE_GE_MIN_PLAYERS)
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
    """ゲーム操作へ外部から渡す依存関係を保持する."""

    repository: GameRepository
    config: GameApplicationConfig
    rule_packs: RulePackRegistry
    create_llm_mode: Literal["fake", "paid"] = "fake"
