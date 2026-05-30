"""API-facing operations for the Streamlit play screen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.contracts.schemas import (
    GameResponse,
    PrivateObservationResponse,
    PublicGameRunSummary,
    SubmitPlayerActionRequest,
)
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    GameScreenView,
    ScreenMode,
    build_game_screen_view,
)
from werewolf_agent.interface.shared import workflows
from werewolf_agent.interface.shared.api_client import GameApiClient, build_game_api_client
from werewolf_agent.interface.shared.game_requests import build_create_game_request


@dataclass(frozen=True)
class AdvanceResult:
    """Result of advancing a game until the player needs to act."""

    reached_input: bool = False
    completed: bool = False
    hit_limit: bool = False


def build_streamlit_client(api_url: str, settings: AppSettings) -> GameApiClient:
    """Build the shared public API client with Streamlit settings."""
    return build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)


def check_connection(*, api_url: str, settings: AppSettings) -> dict[str, str]:
    """Check API health from the Streamlit screen."""
    return workflows.check_health(build_streamlit_client(api_url, settings))


def list_recent_games(*, api_url: str, settings: AppSettings) -> list[PublicGameRunSummary]:
    """Return recent public game runs for the sidebar selector."""
    client = build_streamlit_client(api_url, settings)
    return workflows.list_games(client, limit=settings.streamlit_run_limit).runs


def create_playable_game(
    *,
    api_url: str,
    settings: AppSettings,
    player_count: int,
    seed_text: str,
    human_player_id: str,
) -> GameResponse:
    """Create a game with one human player and return the API response."""
    seed = int(seed_text) if seed_text.strip() else None
    request = build_create_game_request(
        players=player_count,
        seed=seed,
        human_player=human_player_id,
        role_count_entries=[],
        tie_break_policy=settings.game_default_tie_break_policy,
        day_speech_turns=settings.game_default_day_speech_turns,
        allow_self_vote=settings.game_default_allow_self_vote,
        default_player_count=settings.game_default_player_count,
    )
    return workflows.create_game(build_streamlit_client(api_url, settings), request)


def load_game_screen(
    *,
    api_url: str,
    settings: AppSettings,
    game_id: str,
    human_player_id: str | None,
    control_token: str,
    screen_mode: ScreenMode,
) -> GameScreenView:
    """Load public and private data needed by the playable screen."""
    client = build_streamlit_client(api_url, settings)
    state = workflows.get_game(client, game_id).state
    turns = workflows.list_turns(client, game_id, limit=settings.streamlit_turn_limit).turns
    observation = load_observation(
        client=client,
        game_id=game_id,
        human_player_id=human_player_id,
        control_token=control_token,
    )
    return build_game_screen_view(
        state=state,
        turns=turns,
        observation=observation,
        human_player_id=human_player_id,
        screen_mode=screen_mode,
        refresh_interval_seconds=settings.streamlit_refresh_interval_seconds,
    )


def load_observation(
    *,
    client: GameApiClient,
    game_id: str,
    human_player_id: str | None,
    control_token: str,
) -> PrivateObservationResponse | None:
    """Return private observation only when the screen has enough operation context."""
    if not game_id or not human_player_id or not control_token:
        return None
    return workflows.get_private_observation(
        client,
        game_id,
        human_player_id,
        control_token=control_token,
    )


def submit_screen_action(
    *,
    api_url: str,
    settings: AppSettings,
    game_id: str,
    human_player_id: str,
    control_token: str,
    action_type: str,
    target_id: str | None,
    message: str | None,
) -> None:
    """Submit one action selected in the Streamlit hand panel."""
    request = SubmitPlayerActionRequest(
        type=cast(Any, action_type),
        target_id=target_id,
        message=message,
    )
    workflows.submit_player_action(
        build_streamlit_client(api_url, settings),
        game_id,
        human_player_id,
        request,
        control_token=control_token,
    )


def advance_until_input(
    *,
    api_url: str,
    settings: AppSettings,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> AdvanceResult:
    """Advance the game until completion, player input, or the configured limit."""
    client = build_streamlit_client(api_url, settings)
    for _ in range(settings.streamlit_max_auto_steps):
        current = workflows.get_game(client, game_id).state
        if current.status == "completed":
            return AdvanceResult(completed=True)
        observation = load_observation(
            client=client,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )
        if observation is not None and observation.observation.get("available_actions"):
            return AdvanceResult(reached_input=True)
        workflows.step_game(client, game_id)
    return AdvanceResult(hit_limit=True)
