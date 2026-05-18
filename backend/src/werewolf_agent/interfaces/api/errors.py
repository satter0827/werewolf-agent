"""RFC 9457 Problem Details handling for the Django REST API."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError as PydanticValidationError
from rest_framework.exceptions import APIException, ErrorDetail, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from werewolf_agent.errors import (
    AppError,
    ErrorCode,
    InternalError,
    get_error_spec,
    problem_type_uri,
)
from werewolf_agent.errors.schemas import ProblemDetails, ProblemIssue
from werewolf_agent.observation.log_context import get_log_context

PROBLEM_JSON_CONTENT_TYPE = "application/problem+json"

logger = logging.getLogger(__name__)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """Convert API exceptions into RFC 9457 Problem Details responses."""
    request = context.get("request")

    if isinstance(exc, AppError):
        _log_app_error(exc)
        return _problem_response(
            code=exc.code.value,
            title=exc.spec.title,
            status_code=int(exc.spec.status),
            detail=exc.detail,
            request=request,
        )

    if isinstance(exc, PydanticValidationError):
        return _validation_problem_response(
            _pydantic_validation_errors(exc),
            request=request,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, ValidationError):
            return _validation_problem_response(
                _drf_validation_errors(response.data),
                request=request,
                status_code=response.status_code,
            )
        return _drf_problem_response(
            exc,
            response.data,
            request=request,
            status_code=response.status_code,
        )

    internal_error = InternalError()
    logger.exception(
        "Unhandled API exception",
        extra=internal_error.log_extra(trace_id=_trace_id()),
    )
    return _problem_response(
        code=internal_error.code.value,
        title=internal_error.spec.title,
        status_code=int(internal_error.spec.status),
        detail=internal_error.detail,
        request=request,
    )


def bad_request(request: HttpRequest, exception: Exception) -> JsonResponse:
    """Return an RFC 9457 response for Django-level bad requests."""
    return _django_problem_response(
        code="bad_request",
        title=HTTPStatus.BAD_REQUEST.phrase,
        status_code=HTTPStatus.BAD_REQUEST,
        detail="The request could not be understood by the server.",
        request=request,
    )


def permission_denied(request: HttpRequest, exception: Exception) -> JsonResponse:
    """Return an RFC 9457 response for Django-level permission failures."""
    return _django_problem_response(
        code="permission_denied",
        title=HTTPStatus.FORBIDDEN.phrase,
        status_code=HTTPStatus.FORBIDDEN,
        detail="You do not have permission to perform this action.",
        request=request,
    )


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    """Return an RFC 9457 response for Django-level 404s."""
    return _django_problem_response(
        code="not_found",
        title=HTTPStatus.NOT_FOUND.phrase,
        status_code=HTTPStatus.NOT_FOUND,
        detail="The requested resource was not found.",
        request=request,
    )


def server_error(request: HttpRequest) -> JsonResponse:
    """Return an RFC 9457 response for Django-level 500s."""
    error = InternalError()
    return _django_problem_response(
        code=error.code.value,
        title=error.spec.title,
        status_code=error.spec.status,
        detail=error.detail,
        request=request,
    )


def _validation_problem_response(
    errors: list[ProblemIssue],
    *,
    request: Any,
    status_code: int = HTTPStatus.BAD_REQUEST,
) -> Response:
    spec = get_error_spec(ErrorCode.REQUEST_VALIDATION_FAILED)
    return _problem_response(
        code=ErrorCode.REQUEST_VALIDATION_FAILED.value,
        title=spec.title,
        status_code=status_code,
        detail=spec.detail,
        request=request,
        errors=errors,
    )


def _drf_problem_response(
    exc: Exception,
    data: Any,
    *,
    request: Any,
    status_code: int,
) -> Response:
    code = _drf_error_code(exc)
    return _problem_response(
        code=code,
        title=_http_title(status_code),
        status_code=status_code,
        detail=_drf_error_detail(data, fallback=_http_title(status_code)),
        request=request,
    )


def _problem_response(
    *,
    code: str,
    title: str,
    status_code: int,
    detail: str,
    request: Any,
    errors: list[ProblemIssue] | None = None,
) -> Response:
    response = Response(
        _problem_body(
            code=code,
            title=title,
            status_code=status_code,
            detail=detail,
            request=request,
            errors=errors,
        ),
        status=status_code,
        content_type=PROBLEM_JSON_CONTENT_TYPE,
    )
    response["Content-Type"] = PROBLEM_JSON_CONTENT_TYPE
    return response


def _django_problem_response(
    *,
    code: str,
    title: str,
    status_code: HTTPStatus,
    detail: str,
    request: HttpRequest,
) -> JsonResponse:
    return JsonResponse(
        _problem_body(
            code=code,
            title=title,
            status_code=int(status_code),
            detail=detail,
            request=request,
        ),
        status=int(status_code),
        content_type=PROBLEM_JSON_CONTENT_TYPE,
    )


def _problem_body(
    *,
    code: str,
    title: str,
    status_code: int,
    detail: str,
    request: Any,
    errors: list[ProblemIssue] | None = None,
) -> dict[str, Any]:
    return ProblemDetails(
        type=problem_type_uri(code),
        title=title,
        status=status_code,
        detail=detail,
        instance=_request_instance(request),
        code=code,
        trace_id=_trace_id(),
        errors=errors,
    ).model_dump(mode="json", exclude_none=True)


def _pydantic_validation_errors(exc: PydanticValidationError) -> list[ProblemIssue]:
    errors = []
    for error in exc.errors():
        errors.append(
            ProblemIssue(
                code=str(error.get("type", "value_error")),
                detail=str(error.get("msg", "Invalid value.")),
                pointer=_json_pointer(error.get("loc", ())),
            )
        )
    return errors


def _drf_validation_errors(detail: Any) -> list[ProblemIssue]:
    errors = _flatten_drf_errors(detail)
    if errors:
        return errors
    return [ProblemIssue(code="invalid", detail="Invalid value.", pointer="")]


def _flatten_drf_errors(detail: Any, pointer: str = "") -> list[ProblemIssue]:
    if isinstance(detail, ErrorDetail):
        return [
            ProblemIssue(
                code=str(detail.code),
                detail=str(detail),
                pointer=pointer,
            )
        ]
    if isinstance(detail, Mapping):
        errors: list[ProblemIssue] = []
        for key, value in detail.items():
            errors.extend(_flatten_drf_errors(value, _join_pointer(pointer, str(key))))
        return errors
    if isinstance(detail, list):
        if all(isinstance(item, ErrorDetail) for item in detail):
            errors = []
            for item in detail:
                errors.extend(_flatten_drf_errors(item, pointer))
            return errors

        errors = []
        for index, item in enumerate(detail):
            errors.extend(_flatten_drf_errors(item, _join_pointer(pointer, str(index))))
        return errors
    if detail is None:
        return []
    return [ProblemIssue(code="invalid", detail=str(detail), pointer=pointer)]


def _drf_error_code(exc: Exception) -> str:
    if isinstance(exc, APIException):
        code = exc.get_codes()
        if isinstance(code, str):
            return code
    return "error"


def _drf_error_detail(data: Any, *, fallback: str) -> str:
    if isinstance(data, Mapping) and "detail" in data:
        return str(data["detail"])
    if isinstance(data, list):
        return "; ".join(str(item) for item in data) or fallback
    if data is not None:
        return str(data)
    return fallback


def _json_pointer(location: object) -> str:
    if isinstance(location, (tuple, list)):
        segments = [str(segment) for segment in location]
    elif location in (None, ""):
        segments = []
    else:
        segments = [str(location)]
    if not segments:
        return ""
    return "/" + "/".join(_escape_json_pointer_segment(segment) for segment in segments)


def _join_pointer(pointer: str, segment: str) -> str:
    escaped = _escape_json_pointer_segment(segment)
    if not pointer:
        return f"/{escaped}"
    return f"{pointer}/{escaped}"


def _escape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _request_instance(request: Any) -> str:
    if request is None:
        return ""
    get_full_path = getattr(request, "get_full_path", None)
    if callable(get_full_path):
        return str(get_full_path())
    path = getattr(request, "path", "")
    return str(path)


def _http_title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP Error"


def _trace_id() -> str | None:
    return get_log_context().get("trace_id")


def _log_app_error(error: AppError) -> None:
    log_method = logger.warning
    if int(error.spec.status) >= HTTPStatus.INTERNAL_SERVER_ERROR:
        log_method = logger.error
    log_method(
        "Handled API application error",
        extra=error.log_extra(trace_id=_trace_id()),
    )
