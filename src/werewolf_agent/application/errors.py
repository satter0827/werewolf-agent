"""Safe errors and stable codes produced by application use cases."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable identifiers for application failures."""

    CONFIG_INVALID_VALUE = "config.invalid_value"
    REQUEST_VALIDATION_FAILED = "request.validation_failed"
    REQUEST_RATE_LIMITED = "request.rate_limited"
    REQUEST_BODY_TOO_LARGE = "request.body_too_large"
    REQUEST_CONCURRENCY_LIMITED = "request.concurrency_limited"
    REQUEST_INVALID_CONTENT_LENGTH = "request.invalid_content_length"
    REQUEST_TIMED_OUT = "request.timed_out"
    REQUEST_IDEMPOTENCY_CONFLICT = "request.idempotency_conflict"
    REQUEST_METHOD_NOT_ALLOWED = "request.method_not_allowed"
    AUTHENTICATION_REQUIRED = "auth.required"
    AUTHORIZATION_FAILED = "auth.forbidden"
    API_UNAVAILABLE = "api.unavailable"
    RESOURCE_NOT_FOUND = "resource.not_found"
    HTTP_ERROR = "http.error"
    GAME_INVALID_PHASE = "game.invalid_phase"
    GAME_INVALID_ACTION = "game.invalid_action"
    AGENT_INVALID_RESPONSE = "agent.invalid_response"
    LLM_PROVIDER_UNAVAILABLE = "llm.provider_unavailable"
    OBSERVATION_WRITE_FAILED = "observation.write_failed"
    OPERATION_RETRY_EXHAUSTED = "operation.retry_exhausted"
    OPERATION_UPGRADE_INTERRUPTED = "operation.upgrade_interrupted"
    INTERNAL_UNEXPECTED = "internal.unexpected"


_DEFAULT_DETAILS = {
    ErrorCode.CONFIG_INVALID_VALUE: "The application configuration contains an invalid value.",
    ErrorCode.REQUEST_VALIDATION_FAILED: "The request body or parameters failed validation.",
    ErrorCode.REQUEST_RATE_LIMITED: "Wait briefly before trying the request again.",
    ErrorCode.REQUEST_BODY_TOO_LARGE: "The request body exceeds the configured size limit.",
    ErrorCode.REQUEST_CONCURRENCY_LIMITED: "The server is handling its maximum request capacity.",
    ErrorCode.REQUEST_INVALID_CONTENT_LENGTH: "The Content-Length header is invalid.",
    ErrorCode.REQUEST_TIMED_OUT: "The request did not finish within the configured timeout.",
    ErrorCode.REQUEST_IDEMPOTENCY_CONFLICT: (
        "The idempotency key was already used for another request."
    ),
    ErrorCode.REQUEST_METHOD_NOT_ALLOWED: "The requested HTTP method is not allowed.",
    ErrorCode.AUTHENTICATION_REQUIRED: "Authentication is required for this operation.",
    ErrorCode.AUTHORIZATION_FAILED: "The supplied credentials are not valid for this operation.",
    ErrorCode.API_UNAVAILABLE: "The API server could not be reached.",
    ErrorCode.RESOURCE_NOT_FOUND: "The requested resource was not found.",
    ErrorCode.HTTP_ERROR: "The HTTP request could not be completed.",
    ErrorCode.GAME_INVALID_PHASE: "The requested game operation is not valid in the current phase.",
    ErrorCode.GAME_INVALID_ACTION: "The requested game action is not valid.",
    ErrorCode.AGENT_INVALID_RESPONSE: "The agent response could not be validated.",
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: "The configured LLM provider is temporarily unavailable.",
    ErrorCode.OBSERVATION_WRITE_FAILED: "The game event log could not be written.",
    ErrorCode.OPERATION_RETRY_EXHAUSTED: "The operation failed after the configured retry limit.",
    ErrorCode.OPERATION_UPGRADE_INTERRUPTED: "The queued operation must be submitted again.",
    ErrorCode.INTERNAL_UNEXPECTED: "An unexpected internal error occurred.",
}
_RETRYABLE = {
    ErrorCode.REQUEST_RATE_LIMITED,
    ErrorCode.REQUEST_CONCURRENCY_LIMITED,
    ErrorCode.REQUEST_TIMED_OUT,
    ErrorCode.API_UNAVAILABLE,
    ErrorCode.LLM_PROVIDER_UNAVAILABLE,
    ErrorCode.OBSERVATION_WRITE_FAILED,
}


class AppError(Exception):
    """Safe application failure with a stable code and structured context."""

    code = ErrorCode.INTERNAL_UNEXPECTED

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: ErrorCode | None = None,
        context: Mapping[str, object] | None = None,
        retryable: bool | None = None,
    ) -> None:
        """Initialize a safe failure without delivery-specific metadata."""
        self.code = code or self.code
        self.detail = detail or _DEFAULT_DETAILS[self.code]
        self.context = dict(context or {})
        self.retryable = self.code in _RETRYABLE if retryable is None else retryable
        super().__init__(self.detail)

    def log_extra(self, *, trace_id: str | None = None) -> dict[str, object]:
        """Return structured fields for redaction at an outer logging boundary."""
        extra: dict[str, object] = {
            "error_code": self.code.value,
            "error_message": self.detail,
            "retryable": self.retryable,
        }
        if trace_id is not None:
            extra["trace_id"] = trace_id
        if self.context:
            extra["error_context"] = self.context
        return extra


class ConfigError(AppError):
    """Report invalid application configuration."""

    code = ErrorCode.CONFIG_INVALID_VALUE


class GameError(AppError):
    """Report an invalid game operation."""

    code = ErrorCode.GAME_INVALID_ACTION


class GamePhaseError(GameError):
    """Report an operation attempted in the wrong phase."""

    code = ErrorCode.GAME_INVALID_PHASE


class ResourceNotFoundError(AppError):
    """Report a missing application resource."""

    code = ErrorCode.RESOURCE_NOT_FOUND


class GameNotFoundError(LookupError):
    """Report a missing game inside repository-facing handlers."""


class InvalidGameIdError(ValueError):
    """Report an identifier that cannot be parsed as a game ID."""


class AgentError(AppError):
    """Report an invalid agent decision."""

    code = ErrorCode.AGENT_INVALID_RESPONSE


class LlmProviderError(AppError):
    """Report an unavailable configured LLM provider."""

    code = ErrorCode.LLM_PROVIDER_UNAVAILABLE


class ObservationError(AppError):
    """Report a failure to persist observation data."""

    code = ErrorCode.OBSERVATION_WRITE_FAILED


class InternalError(AppError):
    """Report an unexpected internal failure safely."""

    code = ErrorCode.INTERNAL_UNEXPECTED


__all__ = [
    "AgentError",
    "AppError",
    "ConfigError",
    "ErrorCode",
    "GameError",
    "GameNotFoundError",
    "GamePhaseError",
    "InternalError",
    "InvalidGameIdError",
    "LlmProviderError",
    "ObservationError",
    "ResourceNotFoundError",
]
