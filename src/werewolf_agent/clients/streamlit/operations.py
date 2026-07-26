"""Game-client-facing operations for the Streamlit play screen."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import uuid4

from werewolf_agent.adapters.factory import build_game_client
from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.clients.requests import build_create_game_request
from werewolf_agent.clients.streamlit.events import (
    LOG_STREAMLIT_ACTION_SUBMITTED,
    LOG_STREAMLIT_ADVANCE_STEP_COMPLETED,
    LOG_STREAMLIT_ADVANCE_STEP_STARTED,
    LOG_STREAMLIT_GAME_CREATED,
    LOG_STREAMLIT_REFRESHED,
    LOG_STREAMLIT_RERUN_STARTED,
)
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.view_models import (
    GameScreenView,
    ScreenMode,
    build_game_screen_view,
)
from werewolf_agent.contracts.api import PublicRuntimeConfig
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameResponse,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    NarrationMode,
    PlayerActionRequest,
    PlayerObservationResponse,
    PublicGameSummary,
)
from werewolf_agent.observability import bind_observation_context, get_observation_context
from werewolf_agent.observability.constants import EVENT_OUTCOME_SUCCESS
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)


def build_streamlit_client(settings: AppSettings) -> GameClient:
    """Build the shared HTTP game client used by Streamlit."""
    return build_game_client(settings)


def log_streamlit_rerun_started(settings: AppSettings) -> None:
    """Log the Streamlit rerun context without private gameplay data."""
    logger.info(
        LOG_STREAMLIT_RERUN_STARTED,
        extra={
            "event_action": LOG_STREAMLIT_RERUN_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "data_source": "supabase",
            "log_level": settings.log_level,
            "log_output": settings.log_output,
            "log_file_path": str(settings.log_file_path),
            "log_third_party_level": settings.log_third_party_level,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.model,
            "llm_base_url": settings.llm_base_url or "provider default",
        },
    )


def list_recent_games(*, settings: AppSettings) -> list[PublicGameSummary]:
    """Return recent public games for the sidebar selector."""
    client = build_streamlit_client(settings)
    return client.list_games(limit=settings.streamlit_run_limit).games


def load_setup_options(*, settings: AppSettings) -> GameSetupOptionsResponse:
    """Return setup metadata from the active data source."""
    return build_streamlit_client(settings).get_setup_options()


def load_runtime_config(*, settings: AppSettings) -> PublicRuntimeConfig:
    """Return public limits and presentation settings owned by the API."""
    return build_streamlit_client(settings).get_runtime_config()


def create_game_from_setup(
    *,
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
    response = build_streamlit_client(settings).create_game(request)
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
    settings: AppSettings,
    game_id: str,
    manual_player_id: str | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> GameScreenView:
    """Load public and private data needed by the playable screen."""
    client = build_streamlit_client(settings)
    state = client.get_game(game_id).state
    timeline = client.get_timeline(game_id, limit=settings.streamlit_turn_limit).items
    observation = (
        load_observation(
            client=client,
            game_id=game_id,
            manual_player_id=manual_player_id,
        )
        if screen_mode == "playable"
        else None
    )
    screen = build_game_screen_view(
        state=state,
        turns=timeline,
        observation=observation,
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


def load_observation(
    *,
    client: GameClient,
    game_id: str,
    manual_player_id: str | None,
) -> PlayerObservationResponse | None:
    """Return private observation only when the screen has enough operation context."""
    if not game_id or not manual_player_id:
        return None
    return client.get_private_observation(
        game_id,
        manual_player_id,
    )


def submit_screen_action(
    *,
    settings: AppSettings,
    game_id: str,
    manual_player_id: str,
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
    build_streamlit_client(settings).submit_player_action(
        game_id,
        manual_player_id,
        request,
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
    settings: AppSettings,
    game_id: str,
) -> None:
    """Advance the game by one data-source step for Streamlit controls."""
    if get_observation_context().get("trace_id"):
        _advance_one_step(settings=settings, game_id=game_id)
        return
    with bind_observation_context(trace_id=str(uuid4())):
        _advance_one_step(settings=settings, game_id=game_id)


def start_advance_step(
    *,
    settings: AppSettings,
    game_id: str,
) -> AdvanceGameJobResponse:
    """Start a data-source advance job for Streamlit controls."""
    if get_observation_context().get("trace_id"):
        return _start_advance_step(settings=settings, game_id=game_id)
    with bind_observation_context(trace_id=str(uuid4())):
        return _start_advance_step(settings=settings, game_id=game_id)


def load_advance_job(
    *,
    settings: AppSettings,
    game_id: str,
    job_id: str,
) -> AdvanceGameJobResponse:
    """Load one data-source advance job for Streamlit polling."""
    return build_streamlit_client(settings).get_advance_job(game_id, job_id)


def _advance_one_step(
    *,
    settings: AppSettings,
    game_id: str,
) -> None:
    client = build_streamlit_client(settings)
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


def _start_advance_step(
    *,
    settings: AppSettings,
    game_id: str,
) -> AdvanceGameJobResponse:
    client = build_streamlit_client(settings)
    logger.info(
        LOG_STREAMLIT_ADVANCE_STEP_STARTED,
        extra={
            "event_action": LOG_STREAMLIT_ADVANCE_STEP_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
        },
    )
    return client.start_advance_game(game_id)
