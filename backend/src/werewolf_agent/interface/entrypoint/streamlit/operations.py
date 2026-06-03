"""API-facing operations for the Streamlit play screen."""

from __future__ import annotations

import logging
from typing import Any, cast

from werewolf_agent.commons.shared.constants import EVENT_OUTCOME_SUCCESS
from werewolf_agent.commons.shared.messages import (
    LOG_STREAMLIT_ACTION_SUBMITTED,
    LOG_STREAMLIT_ADVANCE_STEP_COMPLETED,
    LOG_STREAMLIT_ADVANCE_STEP_STARTED,
    LOG_STREAMLIT_GAME_CREATED,
    LOG_STREAMLIT_REFRESHED,
    LOG_STREAMLIT_RERUN_STARTED,
)
from werewolf_agent.contracts.schemas import (
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameResponse,
    GameRevealResponse,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    NarrationMode,
    PlayerActionRequest,
    PlayerObservationResponse,
    PublicGameSummary,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    GameScreenView,
    ScreenMode,
    build_game_screen_view,
)
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.api_client import GameApiClient, build_game_api_client
from werewolf_agent.interface.shared.game_requests import build_create_game_request

logger = logging.getLogger(__name__)


def build_streamlit_client(api_url: str, settings: AppSettings) -> GameApiClient:
    """Build the shared public API client with Streamlit settings."""
    return build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)


def log_streamlit_rerun_started(settings: AppSettings) -> None:
    """Log the Streamlit rerun context without private gameplay data."""
    logger.info(
        LOG_STREAMLIT_RERUN_STARTED,
        extra={
            "event_action": LOG_STREAMLIT_RERUN_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "api_url": settings.streamlit_resolved_api_url,
            "save_file_path": str(settings.streamlit_save_file_path),
            "log_level": settings.log_level,
            "log_output": settings.log_output,
            "log_file_path": str(settings.log_file_path),
            "log_third_party_level": settings.log_third_party_level,
        },
    )


def list_recent_games(*, api_url: str, settings: AppSettings) -> list[PublicGameSummary]:
    """Return recent public games for the sidebar selector."""
    client = build_streamlit_client(api_url, settings)
    return client.list_games(limit=settings.streamlit_run_limit).games


def load_setup_options(*, api_url: str, settings: AppSettings) -> GameSetupOptionsResponse:
    """Return setup metadata from the public API."""
    return build_streamlit_client(api_url, settings).get_setup_options()


def create_game_from_setup(
    *,
    api_url: str,
    settings: AppSettings,
    role_counts: dict[str, int],
    rules: LocalRulesSettings,
    seed_text: str,
    manual_player_id: str | None,
    scenario_id: str | None,
    setup_preset_id: str | None,
    narration_mode: NarrationMode,
    character_assignments: dict[str, str],
    custom_roles: list[CustomRoleDefinitionRequest],
    custom_characters: list[CustomCharacterDefinitionRequest],
) -> GameResponse:
    """Create a game from the shared Play/Observe setup."""
    seed = int(seed_text) if seed_text.strip() else None
    request = build_create_game_request(
        seed=seed,
        role_counts=role_counts,
        manual_player_id=manual_player_id,
        rules=rules,
        scenario_id=scenario_id,
        setup_preset_id=setup_preset_id,
        narration_mode=narration_mode,
        character_assignments=character_assignments,
        custom_roles=custom_roles,
        custom_characters=custom_characters,
    )
    response = build_streamlit_client(api_url, settings).create_game(request)
    logger.info(
        LOG_STREAMLIT_GAME_CREATED,
        extra={
            "event_action": LOG_STREAMLIT_GAME_CREATED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": response.game_id,
            "has_manual_player": manual_player_id is not None,
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
    manual_player_id: str | None,
    manual_token: str,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> GameScreenView:
    """Load public and private data needed by the playable screen."""
    client = build_streamlit_client(api_url, settings)
    state = client.get_game(game_id).state
    timeline = client.get_timeline(game_id, limit=settings.streamlit_turn_limit).items
    observation = (
        load_observation(
            client=client,
            game_id=game_id,
            manual_player_id=manual_player_id,
            manual_token=manual_token,
        )
        if screen_mode == "playable"
        else None
    )
    reveal = client.get_game_reveal(game_id) if screen_mode == "observer" else None
    screen = build_game_screen_view(
        state=state,
        turns=timeline,
        observation=observation,
        reveal=reveal,
        manual_player_id=manual_player_id,
        screen_mode=screen_mode,
        catalog=catalog,
        lang=lang,
        refresh_interval_seconds=settings.streamlit_refresh_interval_seconds,
    )
    logger.debug(
        LOG_STREAMLIT_REFRESHED,
        extra={
            "event_action": LOG_STREAMLIT_REFRESHED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "screen_mode": screen_mode,
            "game_status": state.status,
            "game_phase": state.phase,
            "game_day": state.day,
            "game_version": state.version,
            "turn_count": len(timeline),
            "has_observation": observation is not None,
            "available_action_count": len(screen.observation.available_actions)
            if screen.observation is not None
            else 0,
        },
    )
    return screen


def load_reveal(
    *,
    client: GameApiClient,
    game_id: str,
) -> GameRevealResponse:
    """Return full observer information through the dedicated reveal API."""
    return client.get_game_reveal(game_id)


def load_observation(
    *,
    client: GameApiClient,
    game_id: str,
    manual_player_id: str | None,
    manual_token: str,
) -> PlayerObservationResponse | None:
    """Return private observation only when the screen has enough operation context."""
    if not game_id or not manual_player_id or not manual_token:
        return None
    return client.get_private_observation(
        game_id,
        manual_player_id,
        manual_token=manual_token,
    )


def submit_screen_action(
    *,
    api_url: str,
    settings: AppSettings,
    game_id: str,
    manual_player_id: str,
    manual_token: str,
    action_type: str,
    target_id: str | None,
    message: str | None,
) -> None:
    """Submit one action selected in the Streamlit hand panel."""
    request = PlayerActionRequest(
        type=cast(Any, action_type),
        target_id=target_id,
        message=message,
    )
    build_streamlit_client(api_url, settings).submit_player_action(
        game_id,
        manual_player_id,
        request,
        manual_token=manual_token,
    )
    logger.info(
        LOG_STREAMLIT_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_STREAMLIT_ACTION_SUBMITTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "has_target": target_id is not None,
            "has_message": bool(message),
        },
    )


def advance_one_step(
    *,
    api_url: str,
    settings: AppSettings,
    game_id: str,
) -> None:
    """Advance the game by one public API step for Streamlit controls."""
    client = build_streamlit_client(api_url, settings)
    logger.info(
        LOG_STREAMLIT_ADVANCE_STEP_STARTED,
        extra={
            "event_action": LOG_STREAMLIT_ADVANCE_STEP_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
        },
    )
    response = client.advance_game(game_id)
    logger.debug(
        LOG_STREAMLIT_ADVANCE_STEP_COMPLETED,
        extra={
            "event_action": LOG_STREAMLIT_ADVANCE_STEP_COMPLETED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "game_status": response.status,
            "game_phase": response.state.phase,
            "game_day": response.state.day,
            "game_version": response.state.version,
            "event_count": len(response.timeline),
        },
    )
