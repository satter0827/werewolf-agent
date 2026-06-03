"""FastAPI routes for the public API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from werewolf_agent.commons.shared.constants import HEALTH_STATUS_OK
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    AdvanceGameResponse,
    CreateGameRequest,
    GameListQuery,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupOptionsResponse,
    GameTimelineQuery,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
)
from werewolf_agent.interface.api.dependencies import app_settings, game_session_factory
from werewolf_agent.interface.application import games as game_application
from werewolf_agent.interface.application.database import SessionFactory
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.constants import (
    API_PREFIX,
    AUTHORIZATION_HEADER,
    BEARER_AUTH_SCHEME,
    HTTP_CREATED,
)
from werewolf_agent.interface.shared.messages import MESSAGE_AUTHORIZATION_HEADER_REQUIRED

router = APIRouter(prefix=API_PREFIX)
SESSION_FACTORY = Depends(game_session_factory)
APP_SETTINGS = Depends(app_settings)


@router.get("/health")
def health(settings: AppSettings = APP_SETTINGS) -> dict[str, str]:
    """Return API health."""
    return {"status": HEALTH_STATUS_OK, "service": settings.api_service_name}


@router.get("/setup-options", response_model=GameSetupOptionsResponse)
def setup_options(
    settings: AppSettings = APP_SETTINGS,
) -> GameSetupOptionsResponse:
    """Return setup options for game creation."""
    return game_application.get_setup_options(settings=settings)


@router.post(
    "/games",
    response_model=GameResponse,
    response_model_exclude_none=True,
    status_code=HTTP_CREATED,
)
def create_game(
    request: CreateGameRequest,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameResponse:
    """Create a new deterministic game."""
    return game_application.create_game(
        request,
        session_factory=session_factory,
        settings=settings,
    )


@router.get("/games", response_model=GameListResponse)
def list_games(
    status: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameListResponse:
    """Return public game summaries."""
    query = GameListQuery.model_validate({"status": status, "limit": limit, "offset": offset})
    return game_application.list_games(
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
    return game_application.get_game(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.get("/games/{game_id}/reveal", response_model=GameRevealResponse)
def get_game_reveal(
    game_id: str,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameRevealResponse:
    """Return full observer-only game information through the dedicated reveal API."""
    return game_application.get_game_reveal(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.post("/games/{game_id}/advance", response_model=AdvanceGameResponse)
def advance_game(
    game_id: str,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> AdvanceGameResponse:
    """Advance one game by one synchronous use case step."""
    return game_application.advance_game(
        game_id,
        session_factory=session_factory,
        settings=settings,
    )


@router.get("/games/{game_id}/timeline", response_model=GameTimelineResponse)
def game_timeline(
    game_id: str,
    after: int = 0,
    limit: int | None = None,
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> GameTimelineResponse:
    """Return public timeline items after an optional sequence cursor."""
    query = GameTimelineQuery.model_validate({"after": after, "limit": limit})
    return game_application.list_timeline(
        game_id,
        session_factory=session_factory,
        settings=settings,
        after=query.after,
        limit=query.limit,
    )


@router.get(
    "/games/{game_id}/players/{player_id}/observation",
    response_model=PlayerObservationResponse,
)
def player_observation(
    game_id: str,
    player_id: str,
    authorization: str | None = Header(default=None, alias=AUTHORIZATION_HEADER),
    session_factory: SessionFactory = SESSION_FACTORY,
    settings: AppSettings = APP_SETTINGS,
) -> PlayerObservationResponse:
    """Return one authenticated player's private observation."""
    return game_application.get_player_observation(
        game_id,
        player_id,
        session_factory=session_factory,
        settings=settings,
        manual_token=_bearer_token(authorization),
    )


@router.post(
    "/games/{game_id}/players/{player_id}/actions",
    response_model=PlayerActionResponse,
)
def submit_player_action(
    game_id: str,
    player_id: str,
    request: PlayerActionRequest,
    authorization: str | None = Header(default=None, alias=AUTHORIZATION_HEADER),
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
        manual_token=_bearer_token(authorization),
    )


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise AppError(
            MESSAGE_AUTHORIZATION_HEADER_REQUIRED,
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    scheme, separator, token = authorization.strip().partition(" ")
    if separator == "" or scheme.lower() != BEARER_AUTH_SCHEME.lower() or not token.strip():
        raise AppError(
            MESSAGE_AUTHORIZATION_HEADER_REQUIRED,
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    return token.strip()
