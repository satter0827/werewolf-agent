"""Stateless public API workflows shared by interface entry points."""

from __future__ import annotations

from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    GameRunsResponse,
    GameTurnsResponse,
    PrivateObservationResponse,
    RulesetResponse,
    StepGameResponse,
    SubmitPlayerActionRequest,
    SubmitPlayerActionResponse,
)
from werewolf_agent.interface.shared.api_client import GameApiClient


def check_health(client: GameApiClient) -> dict[str, str]:
    """Fetch API health."""
    return client.health()


def get_ruleset(client: GameApiClient) -> RulesetResponse:
    """Fetch the default ruleset."""
    return client.get_ruleset()


def create_game(client: GameApiClient, request: CreateGameRequest) -> GameResponse:
    """Create one game."""
    return client.create_game(request)


def get_game(client: GameApiClient, game_id: str) -> GameResponse:
    """Fetch one game."""
    return client.get_game(game_id)


def step_game(client: GameApiClient, game_id: str) -> StepGameResponse:
    """Advance one game by one API step."""
    return client.step_game(game_id)


def list_events(
    client: GameApiClient,
    game_id: str,
    *,
    after: int = 0,
    limit: int = 100,
) -> GameEventsResponse:
    """Fetch public game events."""
    return client.list_events(game_id, after=after, limit=limit)


def list_turns(
    client: GameApiClient,
    game_id: str,
    *,
    after: int = 0,
    limit: int = 100,
) -> GameTurnsResponse:
    """Fetch public turn history."""
    return client.list_turns(game_id, after=after, limit=limit)


def list_games(
    client: GameApiClient,
    *,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> GameRunsResponse:
    """Fetch public game run summaries."""
    return client.list_games(status=status, limit=limit, offset=offset)


def get_private_observation(
    client: GameApiClient,
    game_id: str,
    player_id: str,
    *,
    control_token: str,
) -> PrivateObservationResponse:
    """Fetch one private observation through the public token API."""
    return client.get_private_observation(
        game_id,
        player_id,
        control_token=control_token,
    )


def submit_player_action(
    client: GameApiClient,
    game_id: str,
    player_id: str,
    request: SubmitPlayerActionRequest,
    *,
    control_token: str,
) -> SubmitPlayerActionResponse:
    """Submit one manual player action through the public token API."""
    return client.submit_player_action(
        game_id,
        player_id,
        request,
        control_token=control_token,
    )
