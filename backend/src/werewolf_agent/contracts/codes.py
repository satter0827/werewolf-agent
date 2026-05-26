"""Stable error codes and public metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from typing import Final

PROBLEM_TYPE_TAG_PREFIX: Final = "tag:werewolf-agent,2026:problem:"


class ErrorCode(StrEnum):
    """Stable machine-readable application error codes."""

    CONFIG_INVALID_VALUE = "config.invalid_value"
    REQUEST_VALIDATION_FAILED = "request.validation_failed"
    API_UNAVAILABLE = "api.unavailable"
    GAME_INVALID_PHASE = "game.invalid_phase"
    GAME_INVALID_ACTION = "game.invalid_action"
    AGENT_INVALID_RESPONSE = "agent.invalid_response"
    LLM_PROVIDER_UNAVAILABLE = "llm.provider_unavailable"
    OBSERVATION_WRITE_FAILED = "observation.write_failed"
    INTERNAL_UNEXPECTED = "internal.unexpected"


@dataclass(frozen=True)
class ErrorSpec:
    """Public metadata for one application error code."""

    title: str
    status: HTTPStatus
    detail: str
    retryable: bool = False


ERROR_SPECS: Final[Mapping[ErrorCode, ErrorSpec]] = {
    ErrorCode.CONFIG_INVALID_VALUE: ErrorSpec(
        title="Invalid Configuration",
        status=HTTPStatus.BAD_REQUEST,
        detail="The application configuration contains an invalid value.",
    ),
    ErrorCode.REQUEST_VALIDATION_FAILED: ErrorSpec(
        title="Request Validation Failed",
        status=HTTPStatus.BAD_REQUEST,
        detail="The request body or parameters failed validation.",
    ),
    ErrorCode.API_UNAVAILABLE: ErrorSpec(
        title="API Unavailable",
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        detail="The API server could not be reached.",
        retryable=True,
    ),
    ErrorCode.GAME_INVALID_PHASE: ErrorSpec(
        title="Invalid Game Phase",
        status=HTTPStatus.CONFLICT,
        detail="The requested game operation is not valid in the current phase.",
    ),
    ErrorCode.GAME_INVALID_ACTION: ErrorSpec(
        title="Invalid Game Action",
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="The requested game action is not valid.",
    ),
    ErrorCode.AGENT_INVALID_RESPONSE: ErrorSpec(
        title="Invalid Agent Response",
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="The agent response could not be validated.",
    ),
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: ErrorSpec(
        title="LLM Provider Unavailable",
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        detail="The configured LLM provider is temporarily unavailable.",
        retryable=True,
    ),
    ErrorCode.OBSERVATION_WRITE_FAILED: ErrorSpec(
        title="Observation Write Failed",
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail="The game event log could not be written.",
        retryable=True,
    ),
    ErrorCode.INTERNAL_UNEXPECTED: ErrorSpec(
        title="Unexpected Internal Error",
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail="An unexpected internal error occurred.",
    ),
}


def get_error_spec(code: ErrorCode) -> ErrorSpec:
    """Return public metadata for an application error code."""
    return ERROR_SPECS[code]


def problem_type_uri(code: ErrorCode | str) -> str:
    """Return the stable RFC 9457 problem type URI for a code."""
    return f"{PROBLEM_TYPE_TAG_PREFIX}{code}"
