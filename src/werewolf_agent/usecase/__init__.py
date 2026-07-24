"""Stateless application operations connecting identifiers to the domain."""

from werewolf_agent.usecase import handlers
from werewolf_agent.usecase.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    CreateGameCommand,
    GameListResult,
    GameResult,
    GameRevealResult,
    GameTimelineResult,
    GetGameQuery,
    GetGameRevealQuery,
    GetPlayerObservationQuery,
    ListGamesQuery,
    ListTimelineQuery,
    PlayerActionCommand,
    PlayerActionResult,
    PlayerObservationResult,
    UsecaseContext,
)


def create_game(context: UsecaseContext, command: CreateGameCommand) -> GameResult:
    """Create one game for a validated user request."""
    return handlers.create_game(command, dependencies=context)


def submit_player_action(
    context: UsecaseContext,
    command: PlayerActionCommand,
) -> PlayerActionResult:
    """Submit one authenticated player action."""
    return handlers.submit_player_action(command, dependencies=context)


def advance_game(
    context: UsecaseContext,
    command: AdvanceGameCommand,
) -> AdvanceGameResult:
    """Advance one game without automated-player orchestration."""
    return handlers.advance_game(command, dependencies=context)


def get_game(context: UsecaseContext, query: GetGameQuery) -> GameResult:
    """Return one public game state."""
    return handlers.get_game(query, dependencies=context)


def get_game_reveal(
    context: UsecaseContext,
    query: GetGameRevealQuery,
) -> GameRevealResult:
    """Return one administrator reveal result."""
    return handlers.get_game_reveal(query, dependencies=context)


def get_player_observation(
    context: UsecaseContext,
    query: GetPlayerObservationQuery,
) -> PlayerObservationResult:
    """Return one authenticated player's observation."""
    return handlers.get_player_observation(query, dependencies=context)


def list_games(context: UsecaseContext, query: ListGamesQuery) -> GameListResult:
    """Return a page of public games."""
    return handlers.list_games(query, dependencies=context)


def list_timeline(
    context: UsecaseContext,
    query: ListTimelineQuery,
) -> GameTimelineResult:
    """Return public timeline items."""
    return handlers.list_timeline(query, dependencies=context)


__all__ = [
    "AdvanceGameCommand",
    "AdvanceGameResult",
    "CreateGameCommand",
    "GameListResult",
    "GameResult",
    "GameRevealResult",
    "GameTimelineResult",
    "GetGameQuery",
    "GetGameRevealQuery",
    "GetPlayerObservationQuery",
    "ListGamesQuery",
    "ListTimelineQuery",
    "PlayerActionCommand",
    "PlayerActionResult",
    "PlayerObservationResult",
    "UsecaseContext",
    "advance_game",
    "create_game",
    "get_game",
    "get_game_reveal",
    "get_player_observation",
    "list_games",
    "list_timeline",
    "submit_player_action",
]
