"""Safe RFC 9457 exception translation."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from werewolf_agent.contracts import (
    AppError,
    ErrorCode,
    GameNotFoundError,
    InvalidGameIdError,
    problem_details_from_error,
    problem_details_from_spec,
)
from werewolf_agent.contracts.error_catalog import get_error_spec
from werewolf_agent.observability.constants import EVENT_OUTCOME_FAILURE
from werewolf_agent.observability.levels import log_level_number

_PROBLEM_STATUSES = (400, 401, 403, 404, 409, 413, 429, 500, 503, 504)
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "description": "RFC 9457 Problem Details",
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemDetails"},
            }
        },
    }
    for status in _PROBLEM_STATUSES
}


def install_error_handlers(app: FastAPI) -> None:
    """Install handlers that never return stack traces or internal exceptions."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        trace_id = _trace_id(request)
        _log_handled_error(request, exc.code, trace_id, error=exc, extra=exc.log_extra())
        return _response(
            problem_details_from_error(
                exc,
                instance=request.url.path,
                trace_id=trace_id,
            )
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del exc
        trace_id = _trace_id(request)
        _log_handled_error(request, ErrorCode.REQUEST_VALIDATION_FAILED, trace_id)
        return _response(
            problem_details_from_spec(
                ErrorCode.REQUEST_VALIDATION_FAILED,
                instance=request.url.path,
                trace_id=trace_id,
            )
        )

    @app.exception_handler(GameNotFoundError)
    async def game_not_found_handler(
        request: Request,
        exc: GameNotFoundError,
    ) -> JSONResponse:
        del exc
        trace_id = _trace_id(request)
        _log_handled_error(request, ErrorCode.RESOURCE_NOT_FOUND, trace_id)
        return _response(
            problem_details_from_spec(
                ErrorCode.RESOURCE_NOT_FOUND,
                instance=request.url.path,
                trace_id=trace_id,
            )
        )

    @app.exception_handler(InvalidGameIdError)
    async def invalid_id_handler(
        request: Request,
        exc: InvalidGameIdError,
    ) -> JSONResponse:
        del exc
        trace_id = _trace_id(request)
        _log_handled_error(request, ErrorCode.REQUEST_VALIDATION_FAILED, trace_id)
        return _response(
            problem_details_from_spec(
                ErrorCode.REQUEST_VALIDATION_FAILED,
                instance=request.url.path,
                trace_id=trace_id,
            )
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id(request)
        spec = get_error_spec(ErrorCode.INTERNAL_UNEXPECTED)
        request.app.state.api_logger.exception(
            "api.request.failed",
            exc_info=exc,
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "event_action": "api.request.failed",
                "event_outcome": EVENT_OUTCOME_FAILURE,
                "error_code": ErrorCode.INTERNAL_UNEXPECTED.value,
                "error_message": spec.detail,
            },
        )
        return _response(
            problem_details_from_spec(
                ErrorCode.INTERNAL_UNEXPECTED,
                instance=request.url.path,
                trace_id=trace_id,
            )
        )


def install_openapi_error_contract(app: FastAPI) -> None:
    """Keep generated clients aligned with the actual validation error boundary."""
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = default_openapi()
        paths = schema.get("paths")
        if not isinstance(paths, dict):
            return schema
        for path, path_item in paths.items():
            if not str(path).startswith("/api/") or not isinstance(path_item, dict):
                continue
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses")
                if isinstance(responses, dict):
                    responses.pop("422", None)
        return schema

    cast(Any, app).openapi = openapi


def _response(problem: object) -> JSONResponse:
    payload = problem.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(
        status_code=int(payload["status"]),
        media_type="application/problem+json",
        content=payload,
    )


def _trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    if trace_id is None:
        trace_id = str(uuid4())
        request.state.trace_id = trace_id
    return str(trace_id)


def _log_handled_error(
    request: Request,
    code: ErrorCode,
    trace_id: str,
    *,
    error: AppError | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    spec = get_error_spec(code)
    exc_info = None
    if code is ErrorCode.INTERNAL_UNEXPECTED and error is not None:
        exc_info = (type(error), error, error.__traceback__)
    request.app.state.api_logger.log(
        log_level_number(spec.log_level),
        "api.application_error.handled",
        exc_info=exc_info,
        extra={
            **(extra or {}),
            "trace_id": trace_id,
            "path": request.url.path,
            "event_action": "api.application_error.handled",
            "event_outcome": EVENT_OUTCOME_FAILURE,
            "error_code": code.value,
            "error_message": spec.detail,
        },
    )


__all__ = ["PROBLEM_RESPONSES", "install_error_handlers", "install_openapi_error_contract"]
