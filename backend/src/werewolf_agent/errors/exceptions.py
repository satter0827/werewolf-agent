"""Application exception classes carrying stable error metadata."""

from __future__ import annotations

from collections.abc import Mapping

from werewolf_agent.errors.codes import ErrorCode, get_error_spec


class AppError(Exception):
    """Base class for safe, user-facing application errors."""

    code: ErrorCode = ErrorCode.INTERNAL_UNEXPECTED

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: ErrorCode | None = None,
        context: Mapping[str, object] | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.code = code or self.code
        self.spec = get_error_spec(self.code)
        self.detail = detail or self.spec.detail
        self.context = dict(context or {})
        self.retryable = self.spec.retryable if retryable is None else retryable
        super().__init__(self.detail)

    def log_extra(self, *, trace_id: str | None = None) -> dict[str, object]:
        """Return structured logging fields for this error."""
        extra: dict[str, object] = {
            "error_code": self.code.value,
            "retryable": self.retryable,
        }
        if trace_id is not None:
            extra["trace_id"] = trace_id
        if self.context:
            extra["error_context"] = self.context
        return extra


class ConfigError(AppError):
    """Configuration is missing or invalid."""

    code = ErrorCode.CONFIG_INVALID_VALUE


class GameError(AppError):
    """Base class for deterministic game rule errors."""

    code = ErrorCode.GAME_INVALID_ACTION


class GamePhaseError(GameError):
    """A game operation was attempted in the wrong phase."""

    code = ErrorCode.GAME_INVALID_PHASE


class AgentError(AppError):
    """An agent returned an invalid or unusable response."""

    code = ErrorCode.AGENT_INVALID_RESPONSE


class LlmProviderError(AppError):
    """The configured LLM provider could not complete a request."""

    code = ErrorCode.LLM_PROVIDER_UNAVAILABLE


class ObservationError(AppError):
    """A replay or observability operation failed."""

    code = ErrorCode.OBSERVATION_WRITE_FAILED


class InternalError(AppError):
    """A safe wrapper for unexpected internal failures."""

    code = ErrorCode.INTERNAL_UNEXPECTED
