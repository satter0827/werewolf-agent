"""Public runtime configuration route."""

from typing import cast

from fastapi import APIRouter, Request

from werewolf_agent.api.dependencies import PrincipalDependency
from werewolf_agent.api.runtime import RuntimeDependencies
from werewolf_agent.application import validate_setup_document
from werewolf_agent.contracts.api import (
    LlmMode,
    PublicRuntimeConfig,
    RuntimeStatusResponse,
    SessionResponse,
    SetupValidationResponse,
)
from werewolf_agent.contracts.schemas import GameSetupDocumentRequest

router = APIRouter(tags=["configuration"])


@router.get(
    "/config",
    response_model=PublicRuntimeConfig,
    operation_id="runtime_config_get",
)
def get_runtime_config(request: Request) -> PublicRuntimeConfig:
    """Return only values safe to expose to every browser."""
    return cast(PublicRuntimeConfig, request.app.state.public_runtime_config)


@router.post(
    "/setups/validate",
    response_model=SetupValidationResponse,
    operation_id="setup_validate",
)
def validate_setup(request: GameSetupDocumentRequest) -> SetupValidationResponse:
    """Validate one complete setup through the canonical application boundary."""
    result = validate_setup_document(request.model_dump(mode="json"))
    return SetupValidationResponse.model_validate(result.model_dump(mode="json"))


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
        llm_mode=cast(LlmMode, principal.llm_mode),
    )
