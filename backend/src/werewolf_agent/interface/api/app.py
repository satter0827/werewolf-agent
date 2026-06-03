"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware

from werewolf_agent.commons.shared.constants import (
    DURATION_MILLISECONDS_DECIMAL_PLACES,
    EVENT_OUTCOME_FAILURE,
    EVENT_OUTCOME_SUCCESS,
    HTTP_FAILURE_STATUS_MIN,
    SECONDS_TO_MILLISECONDS,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.interface.api.routers import router
from werewolf_agent.interface.application.database import (
    create_database_engine,
    create_session_factory,
)
from werewolf_agent.interface.application.models import Base
from werewolf_agent.interface.runtime import (
    AppSettings,
    bind_observation_context,
    configure_interface_logging,
    get_settings,
)
from werewolf_agent.interface.shared.constants import REQUEST_ID_HEADER, TRACE_ID_HEADER
from werewolf_agent.interface.shared.http import (
    app_error_handler,
    http_exception_handler,
    pydantic_validation_error_handler,
    request_validation_error_handler,
    unhandled_exception_handler,
)
from werewolf_agent.interface.shared.log_sanitization import safe_http_log_path
from werewolf_agent.interface.shared.messages import (
    LOG_API_APPLICATION_STARTED,
    LOG_API_REQUEST_COMPLETED,
)

logger = logging.getLogger(__name__)
ApiExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]


def create_app(
    settings: AppSettings | None = None,
    *,
    create_schema: bool = False,
) -> FastAPI:
    """Create the FastAPI ASGI app."""
    loaded_settings = settings or get_settings()
    configure_interface_logging(loaded_settings)
    _log_api_startup(loaded_settings)

    engine = create_database_engine(loaded_settings)
    if create_schema:
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    app = FastAPI(
        title=loaded_settings.api_title,
        version=loaded_settings.api_version,
        debug=loaded_settings.api_debug,
    )
    app.state.settings = loaded_settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    if loaded_settings.cors_allowed_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=loaded_settings.cors_allowed_origins_list,
            allow_credentials=False,
            allow_methods=loaded_settings.cors_allowed_methods_list,
            allow_headers=loaded_settings.cors_allowed_headers_list,
        )

    app.add_exception_handler(AppError, cast(ApiExceptionHandler, app_error_handler))
    app.add_exception_handler(
        RequestValidationError,
        cast(ApiExceptionHandler, request_validation_error_handler),
    )
    app.add_exception_handler(
        PydanticValidationError,
        cast(ApiExceptionHandler, pydantic_validation_error_handler),
    )
    app.add_exception_handler(
        StarletteHTTPException,
        cast(ApiExceptionHandler, http_exception_handler),
    )
    app.add_exception_handler(Exception, cast(ApiExceptionHandler, unhandled_exception_handler))
    app.middleware("http")(_trace_request)
    app.include_router(router)

    return app


def _log_api_startup(settings: AppSettings) -> None:
    startup_fields: dict[str, object] = {
        "event_action": LOG_API_APPLICATION_STARTED,
        "event_outcome": EVENT_OUTCOME_SUCCESS,
        "api_title": settings.api_title,
        "api_version": settings.api_version,
        "api_debug": settings.api_debug,
        "log_level": settings.log_level,
        "log_output": settings.log_output,
        "log_file_path": str(settings.log_file_path),
        "log_third_party_level": settings.log_third_party_level,
    }
    startup_fields.update(_database_log_fields(settings))
    logger.info(LOG_API_APPLICATION_STARTED, extra=startup_fields)


def _database_log_fields(settings: AppSettings) -> dict[str, object]:
    if settings.configured_database_url:
        return {
            "database_backend": _database_backend(settings.sqlalchemy_database_url),
            "database_source": "database_url",
        }
    return {
        "database_backend": "sqlite",
        "database_source": "sqlite_path",
        "sqlite_path": str(settings.sqlite_database_path),
    }


def _database_backend(database_url: str) -> str:
    normalized_url = database_url.lower()
    if normalized_url.startswith("sqlite"):
        return "sqlite"
    if normalized_url.startswith(("postgres://", "postgresql://", "postgresql+")):
        return "postgresql"
    return "configured"


async def _trace_request(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    trace_id = request.headers.get(TRACE_ID_HEADER) or request.headers.get(REQUEST_ID_HEADER)
    trace_id = trace_id.strip() if trace_id is not None else ""
    if not trace_id:
        trace_id = str(uuid4())

    started = time.perf_counter()
    log_path = safe_http_log_path(request.url.path)
    with bind_observation_context(trace_id=trace_id, method=request.method, path=log_path):
        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        logger.info(
            LOG_API_REQUEST_COMPLETED,
            extra={
                "event_action": LOG_API_REQUEST_COMPLETED,
                "event_outcome": (
                    EVENT_OUTCOME_SUCCESS
                    if response.status_code < HTTP_FAILURE_STATUS_MIN
                    else EVENT_OUTCOME_FAILURE
                ),
                "http_method": request.method,
                "http_path": log_path,
                "http_status": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - started) * SECONDS_TO_MILLISECONDS,
                    DURATION_MILLISECONDS_DECIMAL_PLACES,
                ),
            },
        )
        return response
