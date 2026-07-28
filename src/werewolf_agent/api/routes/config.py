"""Public runtime configuration route."""

from typing import cast

from fastapi import APIRouter, Request

from werewolf_agent.api.dependencies import PrincipalDependency
from werewolf_agent.api.runtime import RuntimeDependencies
from werewolf_agent.contracts.api import (
    PublicRuntimeConfig,
    RuntimeStatusResponse,
    SessionResponse,
)

router = APIRouter(tags=["configuration"])


@router.get(
    "/config",
    response_model=PublicRuntimeConfig,
    operation_id="runtime_config_get",
)
def get_runtime_config(request: Request) -> PublicRuntimeConfig:
    """Return only values safe to expose to every browser."""
    return cast(PublicRuntimeConfig, request.app.state.public_runtime_config)


@router.get(
    "/status",
    response_model=RuntimeStatusResponse,
    operation_id="runtime_status_get",
)
def get_runtime_status(request: Request) -> RuntimeStatusResponse:
    """Return sanitized infrastructure availability without authentication."""
    dependencies = cast(RuntimeDependencies, request.app.state.runtime_dependencies)
    return dependencies.public_status()


@router.get(
    "/session",
    response_model=SessionResponse,
    operation_id="session_get",
)
def get_session(principal: PrincipalDependency) -> SessionResponse:
    """Return safe properties of the verified request principal."""
    return SessionResponse(
        anonymous=principal.is_anonymous,
        administrator=principal.is_admin,
        llm_mode=principal.llm_mode,
    )
