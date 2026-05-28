"""RFC 9457 Problem Details handling for the FastAPI interface."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from werewolf_agent.commons.shared.codes import ErrorCode, get_error_spec, problem_type_uri
from werewolf_agent.commons.shared.messages import (
    LOG_API_APPLICATION_ERROR_HANDLED,
    LOG_API_UNHANDLED_EXCEPTION,
    MESSAGE_INVALID_VALUE,
)
from werewolf_agent.contracts import AppError, InternalError
from werewolf_agent.interface.shared.logging import get_log_context
from werewolf_agent.interface.shared.schemas import ProblemDetails, ProblemIssue

PROBLEM_JSON_CONTENT_TYPE = "application/problem+json"

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert application errors into Problem Details responses."""
    _log_app_error(exc)
    return problem_response(
        code=exc.code.value,
        title=exc.spec.title,
        status_code=int(exc.spec.status),
        detail=exc.detail,
        request=request,
    )


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Convert FastAPI validation errors into Problem Details responses."""
    return validation_problem_response(_validation_errors(exc.errors()), request=request)


async def pydantic_validation_error_handler(
    request: Request,
    exc: PydanticValidationError,
) -> JSONResponse:
    """Convert Pydantic validation errors into Problem Details responses."""
    return validation_problem_response(_validation_errors(exc.errors()), request=request)


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Convert HTTP exceptions into Problem Details responses."""
    code = _http_error_code(exc.status_code)
    spec = get_error_spec(code)
    return problem_response(
        code=code.value,
        title=spec.title,
        status_code=exc.status_code,
        detail=spec.detail,
        request=request,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert unexpected exceptions into a safe Problem Details response."""
    error = InternalError()
    logger.exception(
        LOG_API_UNHANDLED_EXCEPTION,
        extra=error.log_extra(trace_id=_trace_id()),
    )
    return problem_response(
        code=error.code.value,
        title=error.spec.title,
        status_code=int(error.spec.status),
        detail=error.detail,
        request=request,
    )


def validation_problem_response(
    errors: list[ProblemIssue],
    *,
    request: Request,
    status_code: int = HTTPStatus.BAD_REQUEST,
) -> JSONResponse:
    """Return a request validation Problem Details response."""
    spec = get_error_spec(ErrorCode.REQUEST_VALIDATION_FAILED)
    return problem_response(
        code=ErrorCode.REQUEST_VALIDATION_FAILED.value,
        title=spec.title,
        status_code=int(status_code),
        detail=spec.detail,
        request=request,
        errors=errors,
    )


def problem_response(
    *,
    code: str,
    title: str,
    status_code: int,
    detail: str,
    request: Request,
    errors: list[ProblemIssue] | None = None,
) -> JSONResponse:
    """Return a Problem Details JSON response."""
    return JSONResponse(
        problem_body(
            code=code,
            title=title,
            status_code=status_code,
            detail=detail,
            request=request,
            errors=errors,
        ),
        status_code=status_code,
        media_type=PROBLEM_JSON_CONTENT_TYPE,
    )


def problem_body(
    *,
    code: str,
    title: str,
    status_code: int,
    detail: str,
    request: Request,
    errors: list[ProblemIssue] | None = None,
) -> dict[str, Any]:
    """Return a Problem Details response body."""
    return ProblemDetails(
        type=problem_type_uri(code),
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
        code=code,
        trace_id=_trace_id(),
        errors=errors,
    ).model_dump(mode="json", exclude_none=True)


def _validation_errors(errors: Sequence[Mapping[str, Any]]) -> list[ProblemIssue]:
    return [
        ProblemIssue(
            code=str(error.get("type", "value_error")),
            detail=str(error.get("msg", MESSAGE_INVALID_VALUE)),
            pointer=_json_pointer(error.get("loc", ())),
        )
        for error in errors
    ]


def _json_pointer(location: object) -> str:
    if isinstance(location, (tuple, list)):
        segments = [str(segment) for segment in location]
    elif location in (None, ""):
        segments = []
    else:
        segments = [str(location)]
    if segments and segments[0] in {"body", "query", "path"}:
        segments = segments[1:]
    if not segments:
        return ""
    return "/" + "/".join(_escape_json_pointer_segment(segment) for segment in segments)


def _escape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _http_error_code(status_code: int) -> ErrorCode:
    if status_code == HTTPStatus.NOT_FOUND:
        return ErrorCode.RESOURCE_NOT_FOUND
    if status_code == HTTPStatus.METHOD_NOT_ALLOWED:
        return ErrorCode.REQUEST_METHOD_NOT_ALLOWED
    return ErrorCode.HTTP_ERROR


def _trace_id() -> str | None:
    return get_log_context().get("trace_id")


def _log_app_error(error: AppError) -> None:
    log_method = logger.warning
    if int(error.spec.status) >= HTTPStatus.INTERNAL_SERVER_ERROR:
        log_method = logger.error
    log_method(
        LOG_API_APPLICATION_ERROR_HANDLED,
        extra=error.log_extra(trace_id=_trace_id()),
    )
