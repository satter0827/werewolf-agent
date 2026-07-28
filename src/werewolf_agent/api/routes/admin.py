"""Administrator-only routes."""

from fastapi import APIRouter, Query

from werewolf_agent.api.dependencies import (
    AdminDiagnostics,
    PrincipalDependency,
    ServicesDependency,
)
from werewolf_agent.api.presenters import reveal_response
from werewolf_agent.application import Actor
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.api import (
    AdminLlmTraceListResponse,
    AdminLlmTraceResponse,
    AdminLlmUsageResponse,
    AdminOperationDiagnosticResponse,
    ReplayVerificationResponse,
)
from werewolf_agent.contracts.schemas import GameRevealResponse

router = APIRouter(prefix="/admin", tags=["administration"])


@router.get(
    "/games/{game_id}/reveal",
    response_model=GameRevealResponse,
    operation_id="admin_game_reveal",
)
def reveal_game(
    game_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> GameRevealResponse:
    """Return complete game state only to an administrator."""
    _require_admin(principal.is_admin)
    if not services.reveal_api_enabled:
        raise AppError(
            "完全状態の取得は無効です。",
            code=ErrorCode.API_UNAVAILABLE,
        )
    result = services.games.reveal(
        game_id,
        Actor(user_id=principal.user_id, is_admin=True),
    )
    return reveal_response(result)


@router.post(
    "/games/{game_id}/replay/verify",
    response_model=ReplayVerificationResponse,
    operation_id="admin_replay_verify",
)
def verify_game_replay(
    game_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> ReplayVerificationResponse:
    """Verify replay checksums without returning private state or events."""
    _require_admin(principal.is_admin)
    result = services.games.verify_replay(
        game_id,
        Actor(user_id=principal.user_id, is_admin=True),
    )
    return ReplayVerificationResponse.model_validate(result.model_dump(mode="json"))


@router.get(
    "/operations/{operation_id}",
    response_model=AdminOperationDiagnosticResponse,
    operation_id="admin_operation_get",
)
def diagnose_operation(
    operation_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> AdminOperationDiagnosticResponse:
    """Return bounded operation diagnostics to administrators."""
    _require_admin(principal.is_admin)
    diagnostics = _diagnostics(services)
    row = diagnostics.operation(operation_id)
    if row is None:
        raise AppError("操作が見つかりません。", code=ErrorCode.RESOURCE_NOT_FOUND)
    payload = dict(row)
    payload["error"] = payload.pop("error_payload", None)
    return AdminOperationDiagnosticResponse.model_validate(payload)


@router.get(
    "/games/{game_id}/llm-traces",
    response_model=AdminLlmTraceListResponse,
    operation_id="admin_llm_traces_get",
)
def list_llm_traces(
    game_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminLlmTraceListResponse:
    """Return trace metadata without prompt or raw response content."""
    _require_admin(principal.is_admin)
    rows = _diagnostics(services).traces(game_id, limit=limit)
    items = []
    for row in rows:
        payload = dict(row)
        payload["error"] = payload.pop("error_payload", None)
        items.append(AdminLlmTraceResponse.model_validate(payload))
    return AdminLlmTraceListResponse(items=items)


@router.get(
    "/games/{game_id}/llm-usage",
    response_model=AdminLlmUsageResponse,
    operation_id="admin_llm_usage_get",
)
def get_llm_usage(
    game_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> AdminLlmUsageResponse:
    """Return aggregate LLM usage without exposing credentials or prompts."""
    _require_admin(principal.is_admin)
    return AdminLlmUsageResponse.model_validate(_diagnostics(services).usage(game_id))


def _require_admin(is_admin: bool) -> None:
    if not is_admin:
        raise AppError(
            "管理者権限が必要です。",
            code=ErrorCode.AUTHORIZATION_FAILED,
        )


def _diagnostics(services: ServicesDependency) -> AdminDiagnostics:
    diagnostics = services.diagnostics
    if diagnostics is None:
        raise AppError("診断機能を利用できません。", code=ErrorCode.API_UNAVAILABLE)
    return diagnostics
