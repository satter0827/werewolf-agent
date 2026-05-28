"""FastAPI routes for the public API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header
from sse_starlette.sse import EventSourceResponse

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameEventsQuery,
    GameEventsResponse,
    GameResponse,
    GameRunsQuery,
    GameRunsResponse,
    GameTurnsQuery,
    GameTurnsResponse,
    PrivateObservationResponse,
    RulesetResponse,
    StepGameResponse,
    SubmitPlayerActionRequest,
    SubmitPlayerActionResponse,
)
from werewolf_agent.interface.api.dependencies import app_settings, game_session_factory
from werewolf_agent.interface.application import games as game_application
from werewolf_agent.interface.application.database import SessionFactory
from werewolf_agent.interface.shared.messages import MESSAGE_AUTHORIZATION_HEADER_REQUIRED

router = APIRouter(prefix="/api/v1")
SESSION_FACTORY = Depends(game_session_factory)
APP_SETTINGS = Depends(app_settings)


@router.get("/health")
def health(settings: AppSettings = APP_SETTINGS) -> dict[str, str]:
    """Return API health."""
    return {"status": "ok", "service": settings.api_service_name}


@router.get("/rulesets/default", response_model=RulesetResponse)
def ruleset_default(
    settings: AppSettings = APP_SETTINGS,
) -> RulesetResponse:
    """Return the default MVP ruleset."""
    return game_application.get_default_ruleset(settings=settings)


@router.post(
    "/games",
    response_model=GameResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_game(
    request: CreateGameRequest,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameResponse:
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


@router.get("/games/{game_id}", response_model=GameResponse, response_model_exclude_none=True)
def get_game(
    game_id: str,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameResponse:
    """Return public game state."""
    return game_application.get_game_run(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.post("/games/{game_id}/steps", response_model=StepGameResponse)
def step_game(
    game_id: str,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> StepGameResponse:
    """Advance one game by one synchronous use case step."""
    return game_application.advance_game_run(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.get(
    "/games/{game_id}/players/{player_id}/observation",
    response_model=PrivateObservationResponse,
)
def private_observation(
    game_id: str,
    player_id: str,
    authorization: str | None = Header(default=None),
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> PrivateObservationResponse:
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
    response_model=SubmitPlayerActionResponse,
)
def submit_player_action(
    game_id: str,
    player_id: str,
    request: SubmitPlayerActionRequest,
    authorization: str | None = Header(default=None),
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> SubmitPlayerActionResponse:
    """Submit one authenticated manual player action."""
    return game_application.submit_player_action(
        game_id,
        player_id,
        request,
        session_factory=session_factory,
        settings=settings,
        control_token=_bearer_token(authorization),
    )


@router.get("/games/{game_id}/events", response_model=GameEventsResponse)
def game_events(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameEventsResponse:
    """Return public game events after an optional sequence cursor."""
    query = GameEventsQuery.model_validate({"after": after, "limit": limit})
    return game_application.list_public_game_events(
        game_id,
        session_factory=session_factory,
        settings=settings,
        after=query.after,
        limit=query.limit,
    )


@router.get("/games/{game_id}/events/stream")
def game_event_stream(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> EventSourceResponse:
    """Return a finite SSE batch of public game events after a cursor."""
    query = GameEventsQuery.model_validate({"after": after, "limit": limit})
    response = game_application.list_public_game_events(
        game_id,
        session_factory=session_factory,
        settings=settings,
        after=query.after,
        limit=query.limit,
    )
    return EventSourceResponse(_event_batch(response))


@router.get("/games/{game_id}/turns", response_model=GameTurnsResponse)
def game_turns(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameTurnsResponse:
    """Return public timeline turns after an optional sequence cursor."""
    query = GameTurnsQuery.model_validate({"after": after, "limit": limit})
    return game_application.list_public_game_turns(
        game_id,
        session_factory=session_factory,
        settings=settings,
        after=query.after,
        limit=query.limit,
    )


async def _event_batch(response: GameEventsResponse) -> AsyncIterator[dict[str, str]]:
    for event in response.events:
        yield {
            "event": "game_event",
            "id": str(event.sequence),
            "data": json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
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
