"""Public common error API for Werewolf Agent."""

from werewolf_agent.commons.codes import (
    ERROR_SPECS,
    PROBLEM_TYPE_TAG_PREFIX,
    ErrorCode,
    ErrorSpec,
    get_error_spec,
    problem_type_uri,
)
from werewolf_agent.commons.exceptions import (
    AgentError,
    AppError,
    ConfigError,
    GameError,
    GamePhaseError,
    InternalError,
    LlmProviderError,
    ObservationError,
)

__all__ = [
    "ERROR_SPECS",
    "PROBLEM_TYPE_TAG_PREFIX",
    "AgentError",
    "AppError",
    "ConfigError",
    "ErrorCode",
    "ErrorSpec",
    "GameError",
    "GamePhaseError",
    "InternalError",
    "LlmProviderError",
    "ObservationError",
    "get_error_spec",
    "problem_type_uri",
]
