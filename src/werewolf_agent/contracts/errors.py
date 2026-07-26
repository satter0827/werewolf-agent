"""Stable error codes, metadata, and Problem Details conversion."""

from __future__ import annotations

from http import HTTPStatus

from werewolf_agent.contracts.error_catalog import (
    ERROR_CONTEXT_HTTP_STATUS,
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_MAX_TOKENS,
    ERROR_CONTEXT_LLM_MODEL,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
    ERROR_CONTEXT_PROBLEM_TYPE,
    ERROR_CONTEXT_SCHEMA,
    ERROR_SPECS,
    LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
    LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
    PROBLEM_TYPE_TAG_PREFIX,
    ErrorCode,
    ErrorLogLevel,
    ErrorSpec,
    ProblemDetailsSource,
    get_error_spec,
    problem_type_uri,
)
from werewolf_agent.contracts.schemas import ProblemDetails, ProblemIssue


def problem_details_from_error(
    error: ProblemDetailsSource,
    *,
    instance: str,
    trace_id: str | None = None,
) -> ProblemDetails:
    """Return public Problem Details for an application error."""
    return problem_details_from_spec(
        error.code,
        instance=instance,
        trace_id=trace_id,
        detail=error.detail,
    )


def problem_details_from_spec(
    code: ErrorCode | str,
    *,
    instance: str,
    trace_id: str | None = None,
    status_code: int | HTTPStatus | None = None,
    detail: str | None = None,
    errors: list[ProblemIssue] | None = None,
) -> ProblemDetails:
    """Return public RFC 9457 Problem Details from stable error metadata."""
    error_code = ErrorCode(code)
    spec = get_error_spec(error_code)
    return ProblemDetails(
        type=problem_type_uri(error_code.value),
        title=spec.title,
        status=int(spec.status if status_code is None else status_code),
        detail=spec.detail if detail is None else detail,
        instance=instance,
        code=error_code.value,
        trace_id=trace_id,
        errors=errors,
        retryable=spec.retryable,
        recovery=spec.recovery,
    )


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
    "problem_details_from_error",
    "problem_details_from_spec",
    "problem_type_uri",
]
