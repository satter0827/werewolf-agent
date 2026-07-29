from typing import cast

from werewolf_agent.application import (
    Actor,
    ApplicationContext,
    ConfigError,
    ErrorCode,
    GameApplication,
    GameApplicationConfig,
    GameRepository,
)

config = GameApplicationConfig(
    min_players=4,
    max_players=16,
    game_list_default_limit=20,
    game_list_max_limit=100,
    timeline_default_limit=50,
    timeline_max_limit=200,
)
context = ApplicationContext(
    repository=cast(GameRepository, object()),
    config=config,
)
games = GameApplication(context)
actor = Actor("user-1")

try:
    games.operation("operation-1", actor)
except ConfigError as error:
    assert error.code is ErrorCode.CONFIG_INVALID_VALUE
