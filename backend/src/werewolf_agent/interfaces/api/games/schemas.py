"""Compatibility re-exports for games API DTOs."""

from werewolf_agent.interfaces.api.schemas import (
    CreateGamePlayer,
    CreateGameRequest,
    GameEventsQuery,
    GameEventsResponse,
    GamePhase,
    GameResponse,
    GameStatus,
    PublicGameEvent,
    PublicGameState,
    PublicPlayerState,
    RulesetResponse,
    StepGameResponse,
    Winner,
)

__all__ = [
    "CreateGamePlayer",
    "CreateGameRequest",
    "GameEventsQuery",
    "GameEventsResponse",
    "GamePhase",
    "GameResponse",
    "GameStatus",
    "PublicGameEvent",
    "PublicGameState",
    "PublicPlayerState",
    "RulesetResponse",
    "StepGameResponse",
    "Winner",
]
