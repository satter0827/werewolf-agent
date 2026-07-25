"""FastAPI composition root."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from werewolf_agent.adapters.application_bridge import (
    build_game_application_config,
    build_game_definitions,
    build_player_setup_definitions,
)
from werewolf_agent.adapters.setup_options import get_local_setup_options
from werewolf_agent.adapters.supabase.diagnostics import SupabaseAdminDiagnostics
from werewolf_agent.adapters.supabase.operations import (
    SupabaseAccessPolicy,
    SupabaseOperationQueue,
)
from werewolf_agent.adapters.supabase.repository import (
    SupabaseGameRepository,
    connect_worker_database,
)
from werewolf_agent.api.dependencies import (
    RequestServices,
    get_principal,
    get_services,
)
from werewolf_agent.api.errors import (
    PROBLEM_RESPONSES,
    install_error_handlers,
    install_openapi_error_contract,
)
from werewolf_agent.api.middleware.limits import PrincipalRateLimiter, RequestLimitsMiddleware
from werewolf_agent.api.middleware.security_headers import ApiSecurityHeadersMiddleware
from werewolf_agent.api.routes import admin, config, games, operations
from werewolf_agent.application import GameApplication
from werewolf_agent.application.models import ApplicationContext
from werewolf_agent.contracts.api import (
    PublicRuntimeConfig,
    PublicRuntimeFeatures,
    PublicRuntimeLimits,
    PublicUiConfig,
)
from werewolf_agent.security.principal import Principal, SupabaseJwtAuthenticator
from werewolf_agent.settings import AppSettings, get_settings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Build the HTTP server and its request-scoped concrete adapters."""
    runtime = settings or get_settings()
    app = FastAPI(
        title="Werewolf Agent API",
        version=runtime.api_contract_version,
        docs_url="/docs" if runtime.api_docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if runtime.api_docs_enabled else None,
        responses=PROBLEM_RESPONSES,
    )
    app.state.authenticator = SupabaseJwtAuthenticator(runtime)
    app.state.principal_rate_limiter = PrincipalRateLimiter(
        request_limit=runtime.api_rate_limit_requests,
        window_seconds=runtime.api_rate_limit_window_seconds,
        max_buckets=max(
            1024,
            runtime.api_rate_limit_requests * runtime.api_max_concurrent_requests * 4,
        ),
    )
    app.state.api_logger = logging.getLogger("werewolf_agent.api")
    app.state.public_runtime_config = _public_runtime_config(runtime)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.api_cors_origin_values,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    app.add_middleware(
        RequestLimitsMiddleware,
        max_body_bytes=runtime.api_max_body_bytes,
        timeout_seconds=runtime.api_timeout_seconds,
        rate_limit_requests=runtime.api_rate_limit_requests,
        rate_limit_window_seconds=runtime.api_rate_limit_window_seconds,
        max_concurrent_requests=runtime.api_max_concurrent_requests,
    )
    app.add_middleware(ApiSecurityHeadersMiddleware)
    install_error_handlers(app)
    app.include_router(config.router, prefix="/api/v1")
    app.include_router(games.router, prefix="/api/v1")
    app.include_router(operations.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    install_openapi_error_contract(app)
    app.dependency_overrides[get_services] = _service_dependency(runtime)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "api"}

    return app


def _service_dependency(
    runtime: AppSettings,
) -> Callable[[Principal], Iterator[RequestServices]]:
    def dependency(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> Iterator[RequestServices]:
        with (
            connect_worker_database(runtime.supabase_db_dsn_value) as connection,
            connection.transaction(),
        ):
            context = ApplicationContext(
                repository=SupabaseGameRepository(
                    connection,
                    owner_user_id=principal.user_id,
                ),
                config=build_game_application_config(runtime),
                game_definitions=build_game_definitions(runtime),
                player_definitions=build_player_setup_definitions(runtime),
            )
            yield RequestServices(
                games=GameApplication(context),
                operations=SupabaseOperationQueue(connection),
                access=SupabaseAccessPolicy(connection),
                message_max_chars=runtime.api_message_max_chars,
                diagnostics=SupabaseAdminDiagnostics(connection),
                reveal_api_enabled=runtime.reveal_api_enabled,
            )

    return dependency


def _public_runtime_config(settings: AppSettings) -> PublicRuntimeConfig:
    return PublicRuntimeConfig(
        contract_version=settings.api_contract_version,
        config_revision=settings.api_config_revision,
        setup=get_local_setup_options(settings),
        limits=PublicRuntimeLimits(
            game_min_players=settings.game_min_players,
            game_max_players=settings.game_max_players,
            message_max_chars=settings.api_message_max_chars,
            game_list_page_size=settings.api_game_list_default_limit,
            timeline_page_size=settings.api_timeline_default_limit,
        ),
        features=PublicRuntimeFeatures(
            authentication=True,
            paid_llm_for_members=True,
            admin_reveal=settings.reveal_api_enabled,
            admin_replay=True,
        ),
        ui=PublicUiConfig(
            theme_id=settings.ui_theme_id,
            spacing_unit=settings.ui_spacing_unit,
            desktop_breakpoint=settings.ui_desktop_breakpoint,
            motion=settings.ui_motion,
            default_manual_player_id=settings.ui_default_manual_player_id,
            default_setup_seed=settings.ui_default_setup_seed,
            operation_poll_interval_ms=settings.ui_operation_poll_interval_ms,
            operation_poll_timeout_ms=settings.ui_operation_poll_timeout_ms,
        ),
    )


__all__ = ["create_app"]
