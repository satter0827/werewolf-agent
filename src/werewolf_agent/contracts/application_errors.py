"""Compatibility exports for application-owned errors."""

from werewolf_agent.application.errors import (
    AgentError,
    AppError,
    ConfigError,
    GameError,
    GameNotFoundError,
    GamePhaseError,
    InternalError,
    InvalidGameIdError,
    LlmProviderError,
    ObservationError,
    ResourceNotFoundError,
)

__all__ = [
    "AgentError",
    "AppError",
    "ConfigError",
    "GameError",
    "GameNotFoundError",
    "GamePhaseError",
    "InternalError",
    "InvalidGameIdError",
    "LlmProviderError",
    "ObservationError",
    "ResourceNotFoundError",
]
