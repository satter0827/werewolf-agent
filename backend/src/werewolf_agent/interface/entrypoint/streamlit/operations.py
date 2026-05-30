"""API-facing operations for the Streamlit play screen."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.commons.shared.messages import (
    LOG_STREAMLIT_ACTION_SUBMITTED,
    LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_ITERATION,
    LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STARTED,
    LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STOPPED,
    LOG_STREAMLIT_CONNECTION_CHECKED,
    LOG_STREAMLIT_GAME_CREATED,
    LOG_STREAMLIT_REFRESHED,
    LOG_STREAMLIT_RERUN_STARTED,
)
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvanceResult:
    """Result of advancing a game until the player needs to act."""

    reached_input: bool = False
    completed: bool = False
    hit_limit: bool = False


def build_streamlit_client(api_url: str, settings: AppSettings) -> GameApiClient:
    """Build the shared public API client with Streamlit settings."""
    return build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)


def log_streamlit_rerun_started(settings: AppSettings) -> None:
    """Log the Streamlit rerun context without private gameplay data."""
    logger.info(
        LOG_STREAMLIT_RERUN_STARTED,
        extra={
            "event_action": LOG_STREAMLIT_RERUN_STARTED,
            "event_outcome": "success",
            "api_url": settings.streamlit_resolved_api_url,
            "save_file_path": str(settings.streamlit_save_file_path),
            "log_level": settings.log_level,
            "log_output": settings.log_output,
            "log_file_path": str(settings.log_file_path),
            "log_third_party_level": settings.log_third_party_level,
        },
    )


def check_connection(*, api_url: str, settings: AppSettings) -> dict[str, str]:
    """Check API health from the Streamlit screen."""
    health = workflows.check_health(build_streamlit_client(api_url, settings))
    logger.info(
        LOG_STREAMLIT_CONNECTION_CHECKED,
        extra={
            "event_action": LOG_STREAMLIT_CONNECTION_CHECKED,
            "event_outcome": "success",
            "api_url": api_url,
        },
    )
    return health


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
    response = workflows.create_game(build_streamlit_client(api_url, settings), request)
    logger.info(
        LOG_STREAMLIT_GAME_CREATED,
        extra={
            "event_action": LOG_STREAMLIT_GAME_CREATED,
            "event_outcome": "success",
            "game_id": response.game_id,
            "player_id": human_player_id,
            "player_count": len(response.state.players),
            "seed": seed,
        },
    )
    return response


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
    screen = build_game_screen_view(
        state=state,
        turns=turns,
        observation=observation,
        human_player_id=human_player_id,
        screen_mode=screen_mode,
        refresh_interval_seconds=settings.streamlit_refresh_interval_seconds,
    )
    logger.debug(
        LOG_STREAMLIT_REFRESHED,
        extra={
            "event_action": LOG_STREAMLIT_REFRESHED,
            "event_outcome": "success",
            "game_id": game_id,
            "player_id": human_player_id,
            "screen_mode": screen_mode,
            "game_status": state.status,
            "game_phase": state.phase,
            "game_day": state.day,
            "game_version": state.version,
            "turn_count": len(turns),
            "has_observation": observation is not None,
            "available_action_count": len(screen.observation.available_actions)
            if screen.observation is not None
            else 0,
        },
    )
    return screen


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
    logger.info(
        LOG_STREAMLIT_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_STREAMLIT_ACTION_SUBMITTED,
            "event_outcome": "success",
            "game_id": game_id,
            "player_id": human_player_id,
            "game_action_type": action_type,
            "has_target": target_id is not None,
            "has_message": bool(message),
        },
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
    logger.info(
        LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STARTED,
        extra={
            "event_action": LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STARTED,
            "event_outcome": "success",
            "game_id": game_id,
            "player_id": human_player_id,
            "max_steps": settings.streamlit_max_auto_steps,
        },
    )
    for iteration in range(settings.streamlit_max_auto_steps):
        current = workflows.get_game(client, game_id).state
        logger.debug(
            LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_ITERATION,
            extra={
                "event_action": LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_ITERATION,
                "event_outcome": "success",
                "game_id": game_id,
                "player_id": human_player_id,
                "iteration": iteration,
                "game_status": current.status,
                "game_phase": current.phase,
                "game_day": current.day,
                "game_version": current.version,
            },
        )
        if current.status == "completed":
            _log_advance_stop(
                game_id=game_id,
                player_id=human_player_id,
                stop_reason="completed",
                iteration=iteration,
            )
            return AdvanceResult(completed=True)
        observation = load_observation(
            client=client,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )
        if observation is not None and observation.observation.get("available_actions"):
            _log_advance_stop(
                game_id=game_id,
                player_id=human_player_id,
                stop_reason="reached_input",
                iteration=iteration,
                available_action_count=len(observation.observation.get("available_actions") or []),
            )
            return AdvanceResult(reached_input=True)
        workflows.step_game(client, game_id)
    _log_advance_stop(
        game_id=game_id,
        player_id=human_player_id,
        stop_reason="hit_limit",
        iteration=settings.streamlit_max_auto_steps,
    )
    return AdvanceResult(hit_limit=True)


def _log_advance_stop(
    *,
    game_id: str,
    player_id: str,
    stop_reason: str,
    iteration: int,
    available_action_count: int = 0,
) -> None:
    logger.info(
        LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STOPPED,
        extra={
            "event_action": LOG_STREAMLIT_ADVANCE_UNTIL_INPUT_STOPPED,
            "event_outcome": "success",
            "game_id": game_id,
            "player_id": player_id,
            "ui_stop_reason": stop_reason,
            "iteration": iteration,
            "available_action_count": available_action_count,
        },
    )
