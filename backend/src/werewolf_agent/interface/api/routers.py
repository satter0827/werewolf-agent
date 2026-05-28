"""FastAPI routes for the public API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from werewolf_agent.interface.application.games import GameApplication
from werewolf_agent.interface.api.dependencies import game_application
from werewolf_agent.interface.shared.schemas import (
    CreateGameRequest,
    GameEventsQuery,
    GameEventsResponse,
    GameResponse,
    GameRunsQuery,
    GameRunsResponse,
    GameTurnsQuery,
    GameTurnsResponse,
    RulesetResponse,
    StepGameResponse,
)
from werewolf_agent.interface.shared.settings import API_SERVICE_NAME

router = APIRouter(prefix="/api/v1")
GAME_APPLICATION = Depends(game_application)


@router.get("/health")
def health() -> dict[str, str]:
    """Return API health."""
    return {"status": "ok", "service": API_SERVICE_NAME}


@router.get("/rulesets/default", response_model=RulesetResponse)
def ruleset_default(
    app: GameApplication = GAME_APPLICATION,
) -> RulesetResponse:
    """Return the default MVP ruleset."""
    return app.default_ruleset()


@router.post("/games", response_model=GameResponse, status_code=201)
def create_game(
    request: CreateGameRequest,
    app: GameApplication = GAME_APPLICATION,
) -> GameResponse:
    """Create a new deterministic game run."""
    return app.create_game_run(request)


@router.get("/games", response_model=GameRunsResponse)
def list_games(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    app: GameApplication = GAME_APPLICATION,
) -> GameRunsResponse:
    """Return public game run summaries."""
    query = GameRunsQuery.model_validate({"status": status, "limit": limit, "offset": offset})
    return app.list_game_runs(status=query.status, limit=query.limit, offset=query.offset)


@router.get("/games/{game_id}", response_model=GameResponse)
def get_game(
    game_id: str,
    app: GameApplication = GAME_APPLICATION,
) -> GameResponse:
    """Return public game state."""
    return app.get_game_run(game_id)


@router.post("/games/{game_id}/steps", response_model=StepGameResponse)
def step_game(
    game_id: str,
    app: GameApplication = GAME_APPLICATION,
) -> StepGameResponse:
    """Advance one game by one synchronous use case step."""
    return app.step_game_run(game_id)


@router.get("/games/{game_id}/events", response_model=GameEventsResponse)
def game_events(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    app: GameApplication = GAME_APPLICATION,
) -> GameEventsResponse:
    """Return public game events after an optional sequence cursor."""
    query = GameEventsQuery.model_validate({"after": after, "limit": limit})
    return app.get_public_events(game_id, after=query.after, limit=query.limit)


@router.get("/games/{game_id}/events/stream")
def game_event_stream(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    app: GameApplication = GAME_APPLICATION,
) -> EventSourceResponse:
    """Return a finite SSE batch of public game events after a cursor."""
    query = GameEventsQuery.model_validate({"after": after, "limit": limit})
    response = app.get_public_events(game_id, after=query.after, limit=query.limit)
    return EventSourceResponse(_event_batch(response))


@router.get("/games/{game_id}/turns", response_model=GameTurnsResponse)
def game_turns(
    game_id: str,
    after: int = 0,
    limit: int = 100,
    app: GameApplication = GAME_APPLICATION,
) -> GameTurnsResponse:
    """Return public timeline turns after an optional sequence cursor."""
    query = GameTurnsQuery.model_validate({"after": after, "limit": limit})
    return app.get_public_turns(game_id, after=query.after, limit=query.limit)


async def _event_batch(response: GameEventsResponse) -> AsyncIterator[dict[str, str]]:
    for event in response.events:
        yield {
            "event": "game_event",
            "id": str(event.sequence),
            "data": json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
        }
