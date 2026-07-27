"""Game-client-facing operations for the Streamlit play screen."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import uuid4

from werewolf_agent.adapters.factory import build_game_client, build_public_client
from werewolf_agent.adapters.ports import GameClient, PublicClient
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
from werewolf_agent.contracts.api import (
    PlayerPreviewRequest,
    PlayerPreviewResponse,
    PublicRuntimeConfig,
    RuntimeStatusResponse,
    SavedSetupListResponse,
    SavedSetupRevisionResponse,
    SessionResponse,
    SetupCatalogResponse,
    SetupCreateRequest,
    SetupRevisionCreateRequest,
    SetupTemplateResponse,
    SetupValidationResponse,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    CreateGameRequest,
    DeliberationLevel,
    GameResponse,
    GameSetupDocumentRequest,
    GameSetupSelectionRequest,
    GameTimelineItem,
    PlayerActionRequest,
    PlayerObservationResponse,
    PublicGameState,
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


def build_streamlit_public_client(settings: AppSettings) -> PublicClient:
    """Build the unauthenticated client used by the Streamlit shell."""
    return build_public_client(settings)


def log_streamlit_rerun_started(settings: AppSettings) -> None:
    """Log the Streamlit rerun context without private gameplay data."""
    logger.debug(
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


def load_public_record(
    *,
    settings: AppSettings,
    game_id: str,
) -> tuple[PublicGameState, list[GameTimelineItem]]:
    """Return the public state and resolved timeline for one record."""
    client = build_streamlit_client(settings)
    state = client.get_game(game_id).state
    timeline = client.get_timeline(game_id, limit=settings.streamlit_turn_limit).items
    return state, timeline


def load_setup_catalog(*, settings: AppSettings) -> SetupCatalogResponse:
    """Return packaged setup metadata for editor and game creation views."""
    return build_streamlit_public_client(settings).get_setup_catalog()


def load_setup_template(*, settings: AppSettings, template_id: str) -> SetupTemplateResponse:
    """Return one complete packaged setup template."""
    return build_streamlit_public_client(settings).get_setup_template(template_id)


def validate_setup(
    *, settings: AppSettings, setup: GameSetupDocumentRequest
) -> SetupValidationResponse:
    """Validate a complete setup through the public API."""
    return build_streamlit_public_client(settings).validate_setup(setup)


def preview_players(
    *, settings: AppSettings, setup: GameSetupSelectionRequest, seed: int | None
) -> PlayerPreviewResponse:
    """Return a deterministic public roster preview."""
    return build_streamlit_public_client(settings).preview_players(
        PlayerPreviewRequest(setup=setup, seed=seed)
    )


def list_saved_setups(*, settings: AppSettings) -> SavedSetupListResponse:
    """Return setups owned by the authenticated user."""
    return build_streamlit_client(settings).list_setups()


def load_saved_setup(
    *, settings: AppSettings, setup_id: str, revision: int | None = None
) -> SavedSetupRevisionResponse:
    """Return the latest or selected revision of an owned setup."""
    client = build_streamlit_client(settings)
    return (
        client.get_setup(setup_id)
        if revision is None
        else client.get_setup_revision(setup_id, revision)
    )


def list_setup_revisions(
    *, settings: AppSettings, setup_id: str
) -> list[SavedSetupRevisionResponse]:
    """Return immutable revision history for an owned setup."""
    return build_streamlit_client(settings).list_setup_revisions(setup_id)


def create_saved_setup(
    *, settings: AppSettings, request: SetupCreateRequest
) -> SavedSetupRevisionResponse:
    """Create an owned setup with its first revision."""
    return build_streamlit_client(settings).create_setup(request)


def create_setup_revision(
    *, settings: AppSettings, setup_id: str, request: SetupRevisionCreateRequest
) -> SavedSetupRevisionResponse:
    """Append an immutable revision to an owned setup."""
    return build_streamlit_client(settings).create_setup_revision(setup_id, request)


def load_runtime_config(*, settings: AppSettings) -> PublicRuntimeConfig:
    """Return public limits and presentation settings owned by the API."""
    return build_streamlit_public_client(settings).get_runtime_config()


def load_runtime_status(*, settings: AppSettings) -> RuntimeStatusResponse:
    """Return public dependency availability for graceful degradation."""
    return build_streamlit_public_client(settings).get_runtime_status()


def load_session(*, settings: AppSettings) -> SessionResponse:
    """Return safe capabilities of the bound authenticated session."""
    return build_streamlit_client(settings).get_session()


def create_game_from_setup(
    *,
    settings: AppSettings,
    setup: GameSetupSelectionRequest,
    seed: int | None,
    manual_player_id: str | None,
    deliberation_level: DeliberationLevel = "standard",
) -> GameResponse:
    """Create a game from one immutable setup selection."""
    request = CreateGameRequest(
        setup=setup,
        seed=seed,
        manual_player_id=manual_player_id,
        deliberation_level=deliberation_level,
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
    ability_id: str | None,
    target_id: str | None,
    message: str | None,
) -> None:
    """Submit one action selected in the Streamlit hand panel."""
    request = PlayerActionRequest(
        type=cast(Any, action_type.split(":", 1)[0]),
        ability_id=ability_id,
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
