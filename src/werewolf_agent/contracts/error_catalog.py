"""Stable error codes and safe metadata."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from werewolf_agent.contracts.messages import (
    DETAIL_AGENT_INVALID_RESPONSE,
    DETAIL_API_UNAVAILABLE,
    DETAIL_AUTHENTICATION_REQUIRED,
    DETAIL_AUTHORIZATION_FAILED,
    DETAIL_CONFIG_INVALID_VALUE,
    DETAIL_GAME_INVALID_ACTION,
    DETAIL_GAME_INVALID_PHASE,
    DETAIL_HTTP_ERROR,
    DETAIL_IDEMPOTENCY_CONFLICT,
    DETAIL_INTERNAL_UNEXPECTED,
    DETAIL_LLM_PROVIDER_UNAVAILABLE,
    DETAIL_METHOD_NOT_ALLOWED,
    DETAIL_OBSERVATION_WRITE_FAILED,
    DETAIL_OPERATION_RETRY_EXHAUSTED,
    DETAIL_OPERATION_UPGRADE_INTERRUPTED,
    DETAIL_REQUEST_BODY_TOO_LARGE,
    DETAIL_REQUEST_CONCURRENCY_LIMITED,
    DETAIL_REQUEST_INVALID_CONTENT_LENGTH,
    DETAIL_REQUEST_RATE_LIMITED,
    DETAIL_REQUEST_TIMED_OUT,
    DETAIL_REQUEST_VALIDATION_FAILED,
    DETAIL_RESOURCE_NOT_FOUND,
    TITLE_API_UNAVAILABLE,
    TITLE_AUTHENTICATION_REQUIRED,
    TITLE_AUTHORIZATION_FAILED,
    TITLE_HTTP_ERROR,
    TITLE_IDEMPOTENCY_CONFLICT,
    TITLE_INVALID_AGENT_RESPONSE,
    TITLE_INVALID_CONFIGURATION,
    TITLE_INVALID_GAME_ACTION,
    TITLE_INVALID_GAME_PHASE,
    TITLE_LLM_PROVIDER_UNAVAILABLE,
    TITLE_METHOD_NOT_ALLOWED,
    TITLE_OBSERVATION_WRITE_FAILED,
    TITLE_OPERATION_RETRY_EXHAUSTED,
    TITLE_OPERATION_UPGRADE_INTERRUPTED,
    TITLE_REQUEST_BODY_TOO_LARGE,
    TITLE_REQUEST_CONCURRENCY_LIMITED,
    TITLE_REQUEST_INVALID_CONTENT_LENGTH,
    TITLE_REQUEST_RATE_LIMITED,
    TITLE_REQUEST_TIMED_OUT,
    TITLE_REQUEST_VALIDATION_FAILED,
    TITLE_RESOURCE_NOT_FOUND,
    TITLE_UNEXPECTED_INTERNAL_ERROR,
)

PROBLEM_TYPE_TAG_PREFIX: Final = "tag:werewolf-agent,2026:problem:"
ERROR_CONTEXT_LLM_ERROR_TYPE: Final = "llm_error_type"
ERROR_CONTEXT_LLM_PROVIDER: Final = "llm_provider"
ERROR_CONTEXT_LLM_MODEL: Final = "llm_model"
ERROR_CONTEXT_LLM_BASE_URL: Final = "llm_base_url"
ERROR_CONTEXT_LLM_TIMEOUT_SECONDS: Final = "llm_timeout_seconds"
ERROR_CONTEXT_LLM_MAX_TOKENS: Final = "llm_max_tokens"
ERROR_CONTEXT_HTTP_STATUS: Final = "http_status"
ERROR_CONTEXT_PROBLEM_TYPE: Final = "problem_type"
ERROR_CONTEXT_SCHEMA: Final = "schema"
LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE: Final = "InvalidModelsResponse"
LLM_PROVIDER_ERROR_NO_LOADED_MODEL: Final = "NoLoadedModel"
ErrorLogLevel = Literal["INFO", "WARNING", "ERROR"]


class ErrorCode(StrEnum):
    """Stable machine-readable application error codes."""

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


class ErrorSpec(BaseModel):
    """Public metadata for one application error code."""

    title: str
    status: HTTPStatus
    detail: str
    retryable: bool = False
    log_level: ErrorLogLevel = "INFO"

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProblemDetailsSource(Protocol):
    """Application error shape needed to build Problem Details."""

    code: ErrorCode
    spec: ErrorSpec
    detail: str


ERROR_SPECS: Final[Mapping[ErrorCode, ErrorSpec]] = {
    ErrorCode.CONFIG_INVALID_VALUE: ErrorSpec(
        title=TITLE_INVALID_CONFIGURATION,
        status=HTTPStatus.BAD_REQUEST,
        detail=DETAIL_CONFIG_INVALID_VALUE,
    ),
    ErrorCode.REQUEST_VALIDATION_FAILED: ErrorSpec(
        title=TITLE_REQUEST_VALIDATION_FAILED,
        status=HTTPStatus.BAD_REQUEST,
        detail=DETAIL_REQUEST_VALIDATION_FAILED,
    ),
    ErrorCode.REQUEST_RATE_LIMITED: ErrorSpec(
        title=TITLE_REQUEST_RATE_LIMITED,
        status=HTTPStatus.TOO_MANY_REQUESTS,
        detail=DETAIL_REQUEST_RATE_LIMITED,
        retryable=True,
        log_level="WARNING",
    ),
    ErrorCode.REQUEST_BODY_TOO_LARGE: ErrorSpec(
        title=TITLE_REQUEST_BODY_TOO_LARGE,
        status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        detail=DETAIL_REQUEST_BODY_TOO_LARGE,
    ),
    ErrorCode.REQUEST_CONCURRENCY_LIMITED: ErrorSpec(
        title=TITLE_REQUEST_CONCURRENCY_LIMITED,
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        detail=DETAIL_REQUEST_CONCURRENCY_LIMITED,
        retryable=True,
        log_level="WARNING",
    ),
    ErrorCode.REQUEST_INVALID_CONTENT_LENGTH: ErrorSpec(
        title=TITLE_REQUEST_INVALID_CONTENT_LENGTH,
        status=HTTPStatus.BAD_REQUEST,
        detail=DETAIL_REQUEST_INVALID_CONTENT_LENGTH,
    ),
    ErrorCode.REQUEST_TIMED_OUT: ErrorSpec(
        title=TITLE_REQUEST_TIMED_OUT,
        status=HTTPStatus.GATEWAY_TIMEOUT,
        detail=DETAIL_REQUEST_TIMED_OUT,
        retryable=True,
        log_level="WARNING",
    ),
    ErrorCode.REQUEST_IDEMPOTENCY_CONFLICT: ErrorSpec(
        title=TITLE_IDEMPOTENCY_CONFLICT,
        status=HTTPStatus.CONFLICT,
        detail=DETAIL_IDEMPOTENCY_CONFLICT,
    ),
    ErrorCode.REQUEST_METHOD_NOT_ALLOWED: ErrorSpec(
        title=TITLE_METHOD_NOT_ALLOWED,
        status=HTTPStatus.METHOD_NOT_ALLOWED,
        detail=DETAIL_METHOD_NOT_ALLOWED,
    ),
    ErrorCode.AUTHENTICATION_REQUIRED: ErrorSpec(
        title=TITLE_AUTHENTICATION_REQUIRED,
        status=HTTPStatus.UNAUTHORIZED,
        detail=DETAIL_AUTHENTICATION_REQUIRED,
    ),
    ErrorCode.AUTHORIZATION_FAILED: ErrorSpec(
        title=TITLE_AUTHORIZATION_FAILED,
        status=HTTPStatus.FORBIDDEN,
        detail=DETAIL_AUTHORIZATION_FAILED,
    ),
    ErrorCode.API_UNAVAILABLE: ErrorSpec(
        title=TITLE_API_UNAVAILABLE,
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        detail=DETAIL_API_UNAVAILABLE,
        retryable=True,
        log_level="WARNING",
    ),
    ErrorCode.RESOURCE_NOT_FOUND: ErrorSpec(
        title=TITLE_RESOURCE_NOT_FOUND,
        status=HTTPStatus.NOT_FOUND,
        detail=DETAIL_RESOURCE_NOT_FOUND,
    ),
    ErrorCode.HTTP_ERROR: ErrorSpec(
        title=TITLE_HTTP_ERROR,
        status=HTTPStatus.BAD_REQUEST,
        detail=DETAIL_HTTP_ERROR,
    ),
    ErrorCode.GAME_INVALID_PHASE: ErrorSpec(
        title=TITLE_INVALID_GAME_PHASE,
        status=HTTPStatus.CONFLICT,
        detail=DETAIL_GAME_INVALID_PHASE,
    ),
    ErrorCode.GAME_INVALID_ACTION: ErrorSpec(
        title=TITLE_INVALID_GAME_ACTION,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail=DETAIL_GAME_INVALID_ACTION,
    ),
    ErrorCode.AGENT_INVALID_RESPONSE: ErrorSpec(
        title=TITLE_INVALID_AGENT_RESPONSE,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail=DETAIL_AGENT_INVALID_RESPONSE,
        log_level="WARNING",
    ),
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: ErrorSpec(
        title=TITLE_LLM_PROVIDER_UNAVAILABLE,
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        detail=DETAIL_LLM_PROVIDER_UNAVAILABLE,
        retryable=True,
        log_level="WARNING",
    ),
    ErrorCode.OBSERVATION_WRITE_FAILED: ErrorSpec(
        title=TITLE_OBSERVATION_WRITE_FAILED,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail=DETAIL_OBSERVATION_WRITE_FAILED,
        retryable=True,
        log_level="WARNING",
    ),
    ErrorCode.OPERATION_RETRY_EXHAUSTED: ErrorSpec(
        title=TITLE_OPERATION_RETRY_EXHAUSTED,
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        detail=DETAIL_OPERATION_RETRY_EXHAUSTED,
        log_level="ERROR",
    ),
    ErrorCode.OPERATION_UPGRADE_INTERRUPTED: ErrorSpec(
        title=TITLE_OPERATION_UPGRADE_INTERRUPTED,
        status=HTTPStatus.CONFLICT,
        detail=DETAIL_OPERATION_UPGRADE_INTERRUPTED,
        log_level="WARNING",
    ),
    ErrorCode.INTERNAL_UNEXPECTED: ErrorSpec(
        title=TITLE_UNEXPECTED_INTERNAL_ERROR,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail=DETAIL_INTERNAL_UNEXPECTED,
        log_level="ERROR",
    ),
}


def get_error_spec(code: ErrorCode) -> ErrorSpec:
    """Return public metadata for an application error code."""
    return ERROR_SPECS[code]


def problem_type_uri(code: ErrorCode | str) -> str:
    """Return the stable RFC 9457 problem type URI for a code."""
    return f"{PROBLEM_TYPE_TAG_PREFIX}{code}"


__all__ = [
    "ERROR_CONTEXT_HTTP_STATUS",
    "ERROR_CONTEXT_LLM_BASE_URL",
    "ERROR_CONTEXT_LLM_ERROR_TYPE",
    "ERROR_CONTEXT_LLM_MAX_TOKENS",
    "ERROR_CONTEXT_LLM_MODEL",
    "ERROR_CONTEXT_LLM_PROVIDER",
    "ERROR_CONTEXT_LLM_TIMEOUT_SECONDS",
    "ERROR_CONTEXT_PROBLEM_TYPE",
    "ERROR_CONTEXT_SCHEMA",
    "ERROR_SPECS",
    "LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE",
    "LLM_PROVIDER_ERROR_NO_LOADED_MODEL",
    "PROBLEM_TYPE_TAG_PREFIX",
    "ErrorCode",
    "ErrorLogLevel",
    "ErrorSpec",
    "ProblemDetailsSource",
    "get_error_spec",
    "problem_type_uri",
]
