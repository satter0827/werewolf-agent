"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware

from werewolf_agent.contracts import AppError
from werewolf_agent.interface.application.database import (
    create_database_engine,
    create_session_factory,
)
from werewolf_agent.interface.application.games import GameApplication
from werewolf_agent.interface.application.models import Base
from werewolf_agent.interface.entrypoint.api.errors import (
    app_error_handler,
    http_exception_handler,
    pydantic_validation_error_handler,
    request_validation_error_handler,
    unhandled_exception_handler,
)
from werewolf_agent.interface.entrypoint.api.routers import router
from werewolf_agent.interface.shared.logging import bind_log_context
from werewolf_agent.interface.shared.runtime import configure_interface_logging
from werewolf_agent.interface.shared.settings import AppSettings, get_settings

TRACE_ID_HEADER = "X-Trace-Id"
REQUEST_ID_HEADER = "X-Request-Id"

logger = logging.getLogger(__name__)


def create_app(
    settings: AppSettings | None = None,
    *,
    create_schema: bool = False,
) -> FastAPI:
    """Create the FastAPI ASGI app."""
    loaded_settings = settings or get_settings()
    configure_interface_logging(loaded_settings)

    engine = create_database_engine(loaded_settings)
    if create_schema:
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    app = FastAPI(
        title="Werewolf Agent API",
        version="0.1.0",
        debug=loaded_settings.api_debug,
    )
    app.state.settings = loaded_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.game_application = GameApplication(
        session_factory=session_factory,
        settings=loaded_settings,
    )

    if loaded_settings.cors_allowed_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=loaded_settings.cors_allowed_origins_list,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(PydanticValidationError, pydantic_validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.middleware("http")(_trace_request)
    app.include_router(router)

    return app


async def _trace_request(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    trace_id = request.headers.get(TRACE_ID_HEADER) or request.headers.get(REQUEST_ID_HEADER)
    trace_id = trace_id.strip() if trace_id is not None else ""
    if not trace_id:
        trace_id = str(uuid4())

    started = time.perf_counter()
    with bind_log_context(trace_id=trace_id, method=request.method, path=request.url.path):
        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        logger.info(
            "API request completed",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return response
