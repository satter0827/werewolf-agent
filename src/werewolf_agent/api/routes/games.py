"""Public and player-private game routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query, status

from werewolf_agent.api.dependencies import PrincipalDependency, ServicesDependency
from werewolf_agent.api.presenters import (
    game_list_response,
    game_response,
    observation_response,
    operation_response,
    timeline_response,
)
from werewolf_agent.api.routes.setups import resolve_setup
from werewolf_agent.application import Actor
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.api import (
    AdvanceOperationRequest,
    OperationResponse,
    PlayerActionOperationRequest,
)
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameStatus,
    GameTimelineResponse,
    PlayerObservationResponse,
)

router = APIRouter(tags=["games"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]
GameStatusFilter = Annotated[GameStatus | None, Query(alias="status")]
LimitQuery = Annotated[int | None, Query(ge=1)]
OffsetQuery = Annotated[int, Query(ge=0)]


@router.post(
    "/games",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="game_create",
)
def create_game(
    request: CreateGameRequest,
    idempotency_key: IdempotencyKey,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> OperationResponse:
    """Queue one game with a server-selected immutable LLM mode."""
    actor = Actor(
        user_id=principal.user_id,
        is_anonymous=principal.is_anonymous,
        is_admin=principal.is_admin,
    )
    command = services.setups.prepare_create(
        resolve_setup(request.setup, principal, services),
        seed=request.seed,
        manual_player_id=request.manual_player_id,
        llm_mode=principal.llm_mode,
        deliberation_level=request.deliberation_level,
    )
    operation = services.games.enqueue_create(
        actor,
        idempotency_key=idempotency_key,
        request_payload=command.model_dump(mode="json", exclude_none=True),
        llm_mode=principal.llm_mode,
    )
    return operation_response(operation)


@router.get(
    "/games",
    response_model=GameListResponse,
    response_model_exclude_none=True,
    operation_id="game_list",
)
def list_games(
    principal: PrincipalDependency,
    services: ServicesDependency,
    game_status: GameStatusFilter = None,
    limit: LimitQuery = None,
    offset: OffsetQuery = 0,
) -> GameListResponse:
    """Return games visible through the caller's application projection."""
    result = services.games.list(
        Actor(
            user_id=principal.user_id,
            is_anonymous=principal.is_anonymous,
            is_admin=principal.is_admin,
        ),
        status=game_status,
        limit=limit,
        offset=offset,
    )
    return game_list_response(result)


@router.get(
    "/games/{game_id}",
    response_model=GameResponse,
    response_model_exclude_none=True,
    operation_id="game_get",
)
def get_game(
    game_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> GameResponse:
    """Return one authorized public game state."""
    result = services.games.get(game_id, Actor(user_id=principal.user_id))
    return game_response(result)


@router.get(
    "/games/{game_id}/timeline",
    response_model=GameTimelineResponse,
    operation_id="game_timeline_get",
)
def get_timeline(
    game_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
    after: int = Query(default=0, ge=0),
    limit: LimitQuery = None,
) -> GameTimelineResponse:
    """Return authorized public timeline items."""
    result = services.games.timeline(
        game_id,
        Actor(user_id=principal.user_id),
        after,
        limit=limit,
    )
    return timeline_response(result)


@router.get(
    "/games/{game_id}/observation/{player_id}",
    response_model=PlayerObservationResponse,
    operation_id="game_observation_get",
)
def get_observation(
    game_id: str,
    player_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> PlayerObservationResponse:
    """Return only the requesting player's private projection."""
    result = services.games.observation(
        game_id,
        Actor(user_id=principal.user_id),
        player_id,
    )
    return observation_response(result)


@router.post(
    "/games/{game_id}/actions",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="game_action_submit",
)
def submit_action(
    game_id: str,
    request: PlayerActionOperationRequest,
    idempotency_key: IdempotencyKey,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> OperationResponse:
    """Queue one version-checked player action."""
    _validate_action_text(request, services.message_max_chars)
    operation = services.games.enqueue_action(
        game_id,
        Actor(user_id=principal.user_id),
        player_id=request.player_id,
        expected_version=request.expected_version,
        idempotency_key=idempotency_key,
        request_payload=request.action.model_dump(mode="json", exclude_none=True),
    )
    return operation_response(operation)


def _validate_action_text(request: PlayerActionOperationRequest, max_chars: int) -> None:
    for value in (
        getattr(request.action, "message", None),
        getattr(request.action, "reason", None),
    ):
        if value is not None and len(value) > max_chars:
            raise AppError(
                f"入力できる文章は{max_chars}文字までです。",
                code=ErrorCode.REQUEST_VALIDATION_FAILED,
            )


@router.post(
    "/games/{game_id}/advance",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="game_advance",
)
def advance_game(
    game_id: str,
    request: AdvanceOperationRequest,
    idempotency_key: IdempotencyKey,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> OperationResponse:
    """Queue one authorized version-checked game advance."""
    operation = services.games.enqueue_advance(
        game_id,
        Actor(user_id=principal.user_id),
        expected_version=request.expected_version,
        idempotency_key=idempotency_key,
    )
    return operation_response(operation)
