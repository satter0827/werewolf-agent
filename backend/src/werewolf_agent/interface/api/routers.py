"""FastAPI routes for the public API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query
from sse_starlette.sse import EventSourceResponse

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    AdvanceGameRunResponse,
    AdvanceUntilInputResponse,
    CreateGameRunRequest,
    GameRunResponse,
    GameRunsQuery,
    GameRunsResponse,
    GameTimelineQuery,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
    RulesetResponse,
)
from werewolf_agent.interface.api.dependencies import app_settings, game_session_factory
from werewolf_agent.interface.application import games as game_application
from werewolf_agent.interface.application.database import SessionFactory
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.messages import MESSAGE_AUTHORIZATION_HEADER_REQUIRED

router = APIRouter(prefix="/api/v1")
SESSION_FACTORY = Depends(game_session_factory)
APP_SETTINGS = Depends(app_settings)


@router.get("/health")
def health(settings: AppSettings = APP_SETTINGS) -> dict[str, str]:
    """Return API health."""
    return {"status": "ok", "service": settings.api_service_name}


@router.get("/ruleset", response_model=RulesetResponse)
def ruleset(
    settings: AppSettings = APP_SETTINGS,
) -> RulesetResponse:
    """Return the default ruleset."""
    return game_application.get_default_ruleset(settings=settings)


@router.post(
    "/games",
    response_model=GameRunResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_game(
    request: CreateGameRunRequest,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameRunResponse:
    """Create a new deterministic game run."""
    return game_application.create_game_run(
        request,
        session_factory=session_factory,
        settings=settings,
    )


@router.get("/games", response_model=GameRunsResponse)
def list_games(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameRunsResponse:
    """Return public game run summaries."""
    query = GameRunsQuery.model_validate({"status": status, "limit": limit, "offset": offset})
    return game_application.list_game_runs(
        session_factory=session_factory,
        settings=settings,
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/games/{game_id}", response_model=GameRunResponse, response_model_exclude_none=True)
def get_game(
    game_id: str,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameRunResponse:
    """Return public game state."""
    return game_application.get_game_run(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.post("/games/{game_id}/advance", response_model=AdvanceGameRunResponse)
def advance_game(
    game_id: str,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> AdvanceGameRunResponse:
    """Advance one game by one synchronous use case step."""
    return game_application.advance_game_run(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.post("/games/{game_id}/advance-until-input", response_model=AdvanceUntilInputResponse)
def advance_until_input(
    game_id: str,
    max_steps: int | None = Query(default=None, ge=1),
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> AdvanceUntilInputResponse:
    """Advance a game until manual input, completion, or the configured step limit."""
    return game_application.advance_until_input(
        game_id,
        session_factory=session_factory,
        settings=settings,
        max_steps=max_steps,
    )


@router.get("/games/{game_id}/timeline", response_model=GameTimelineResponse)
def game_timeline(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameTimelineResponse:
    """Return public timeline items after an optional sequence cursor."""
    query = GameTimelineQuery.model_validate({"after": after, "limit": limit})
    return game_application.get_game_timeline(
        game_id,
        session_factory=session_factory,
        settings=settings,
        after=query.after,
        limit=query.limit,
    )


@router.get("/games/{game_id}/timeline/stream")
def game_timeline_stream(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> EventSourceResponse:
    """Return a finite SSE batch of public timeline items after a cursor."""
    query = GameTimelineQuery.model_validate({"after": after, "limit": limit})
    response = game_application.get_game_timeline(
        game_id,
        session_factory=session_factory,
        settings=settings,
        after=query.after,
        limit=query.limit,
    )
    return EventSourceResponse(_timeline_batch(response))


@router.get(
    "/games/{game_id}/players/{player_id}/observation",
    response_model=PlayerObservationResponse,
)
def player_observation(
    game_id: str,
    player_id: str,
    authorization: str | None = Header(default=None),
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> PlayerObservationResponse:
    """Return one authenticated player's private observation."""
    return game_application.get_player_observation(
        game_id,
        player_id,
        session_factory=session_factory,
        settings=settings,
        control_token=_bearer_token(authorization),
    )


@router.post(
    "/games/{game_id}/players/{player_id}/actions",
    response_model=PlayerActionResponse,
)
def submit_player_action(
    game_id: str,
    player_id: str,
    request: PlayerActionRequest,
    authorization: str | None = Header(default=None),
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> PlayerActionResponse:
    """Submit one authenticated manual player action."""
    return game_application.submit_player_action(
        game_id,
        player_id,
        request,
        session_factory=session_factory,
        settings=settings,
        control_token=_bearer_token(authorization),
    )


async def _timeline_batch(response: GameTimelineResponse) -> AsyncIterator[dict[str, str]]:
    for item in response.items:
        yield {
            "event": "timeline_item",
            "id": str(item.sequence),
            "data": json.dumps(item.model_dump(mode="json"), ensure_ascii=False),
        }


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise AppError(
            MESSAGE_AUTHORIZATION_HEADER_REQUIRED,
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    scheme, separator, token = authorization.strip().partition(" ")
    if separator == "" or scheme.lower() != "bearer" or not token.strip():
        raise AppError(
            MESSAGE_AUTHORIZATION_HEADER_REQUIRED,
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    return token.strip()
