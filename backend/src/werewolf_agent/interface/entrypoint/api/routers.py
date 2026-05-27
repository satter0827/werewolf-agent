"""FastAPI routes for the public API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from werewolf_agent.interface.application.games import GameApplication
from werewolf_agent.interface.entrypoint.api.dependencies import game_application
from werewolf_agent.interface.shared.schemas import (
    CreateGameRequest,
    GameEventsQuery,
    GameEventsResponse,
    GameResponse,
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
    app: GameApplication = GAME_APPLICATION,
) -> GameEventsResponse:
    """Return public game events after an optional sequence cursor."""
    query = GameEventsQuery.model_validate({"after": after})
    return app.get_public_events(game_id, after=query.after)


@router.get("/games/{game_id}/events/stream")
def game_event_stream(
    game_id: str,
    after: int = 0,
    app: GameApplication = GAME_APPLICATION,
) -> EventSourceResponse:
    """Return a finite SSE batch of public game events after a cursor."""
    query = GameEventsQuery.model_validate({"after": after})
    response = app.get_public_events(game_id, after=query.after)
    return EventSourceResponse(_event_batch(response))


async def _event_batch(response: GameEventsResponse) -> AsyncIterator[dict[str, str]]:
    for event in response.events:
        yield {
            "event": "game_event",
            "id": str(event.sequence),
            "data": json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
        }
