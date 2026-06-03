"""Stateless interface application bridge for game use cases."""

from __future__ import annotations

import logging
from typing import TypeVar, cast

from pydantic import BaseModel
from sqlalchemy.orm import Session

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.commons.shared.constants import EVENT_OUTCOME_SUCCESS, MIN_PAGE_LIMIT
from werewolf_agent.commons.shared.definitions import (
    CustomCharacterDefinition,
    CustomRoleDefinition,
)
from werewolf_agent.commons.shared.messages import (
    LOG_GAME_CREATED,
    LOG_GAME_STEPPED,
    LOG_GAME_TIMELINE_LISTED,
    LOG_GAMES_LISTED,
    LOG_PLAYER_ACTION_SUBMITTED,
    LOG_PRIVATE_OBSERVATION_RETURNED,
    MESSAGE_GAME_NOT_FOUND,
    message_field_must_be_between,
)
from werewolf_agent.contracts import (
    AppError,
    GameNotFoundError,
    InvalidGameIdError,
    ResourceNotFoundError,
)
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    AbilityDefinitionView,
    AdvanceGameResponse,
    CharacterDefinitionView,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupOptionsResponse,
    GameTimelineResponse,
    LocalRulesSettings,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
    RoleDefinitionView,
    ScenarioDefinitionView,
    SetupPresetDefinitionView,
)
from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.repositories import SqlAlchemyGameRepository
from werewolf_agent.interface.application.settings import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
    build_llm_provider_config,
)
from werewolf_agent.interface.application.telemetry import LoggingTelemetrySink
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.messages import MESSAGE_REVEAL_API_DISABLED

TModel = TypeVar("TModel", bound=BaseModel)
logger = logging.getLogger(__name__)


def get_setup_options(*, settings: AppSettings) -> GameSetupOptionsResponse:
    """Return public setup options.

    Args:
        settings: Loaded application settings.

    Returns:
        Wire schema containing setup metadata and display names.

    """
    options = game_jobs.GameService.get_setup_options(
        build_game_usecase_config(settings),
        build_game_definitions(settings),
        build_llm_definitions(settings),
    )
    return _setup_options_response(options, settings)


def create_game(
    request: CreateGameRequest,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameResponse:
    """Create and persist one deterministic game.

    Args:
        request: Validated HTTP request body.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.

    Returns:
        Public game response for API and CUI clients.

    """
    command = _create_command(request, settings)
    with session_scope(session_factory) as session:
        response = _use_cases(session, settings).create_game(command)
    logger.info(
        LOG_GAME_CREATED,
        extra={
            "event_action": LOG_GAME_CREATED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": response.game_id,
            "player_count": request.player_count,
        },
    )
    return _wire_model(GameResponse, response)


def get_game(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameResponse:
    """Return the current public state for one game.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.

    Returns:
        Public game response.

    Raises:
        ResourceNotFoundError: If the id is invalid or the game is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_game(
                game_jobs.GetGameQuery(game_id=game_id)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    return _wire_model(GameResponse, response)


def get_game_reveal(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameRevealResponse:
    """Return full observer-only game information when reveal API is enabled."""
    if not settings.reveal_api_enabled:
        raise AppError(MESSAGE_REVEAL_API_DISABLED, code=ErrorCode.AUTHORIZATION_FAILED)
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_game_reveal(
                game_jobs.GetGameRevealQuery(game_id=game_id)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    return _wire_model(GameRevealResponse, response)


def list_games(
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    status: game_jobs.GameStatus | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> GameListResponse:
    """Return public game summaries.

    Args:
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        status: Optional public game status filter.
        limit: Maximum number of rows to return.
        offset: Result offset for pagination.

    Returns:
        Public game summaries and pagination metadata.

    """
    resolved_limit = _api_page_limit(
        limit,
        default=settings.api_game_list_default_limit,
        maximum=settings.api_game_list_max_limit,
        field_name="limit",
    )
    with session_scope(session_factory) as session:
        response = _use_cases(session, settings).list_games(
            game_jobs.ListGamesQuery(status=status, limit=resolved_limit, offset=offset)
        )
    logger.debug(
        LOG_GAMES_LISTED,
        extra={
            "event_action": LOG_GAMES_LISTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_status": status,
            "limit": resolved_limit,
            "offset": offset,
            "count": len(response.games),
        },
    )
    return _wire_model(GameListResponse, response)


def advance_game(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> AdvanceGameResponse:
    """Advance one game by one deterministic use case step.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.

    Returns:
        Updated public state and emitted public timeline items.

    Raises:
        ResourceNotFoundError: If the id is invalid or the game is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).advance_game(
                game_jobs.AdvanceGameCommand(game_id=game_id)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_GAME_STEPPED,
        extra={
            "event_action": LOG_GAME_STEPPED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": response.game_id,
            "game_status": response.status,
            "game_phase": response.state.get("phase"),
            "game_day": response.state.get("day"),
            "game_version": response.state.get("version"),
            "event_count": len(response.timeline),
        },
    )
    return _wire_model(AdvanceGameResponse, response)


def list_timeline(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    after: int = 0,
    limit: int | None = None,
) -> GameTimelineResponse:
    """List public timeline items after a sequence number.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        after: Exclusive sequence cursor.
        limit: Maximum number of timeline items to return.

    Returns:
        Public timeline items and the next sequence cursor.

    Raises:
        ResourceNotFoundError: If the id is invalid or the game is absent.

    """
    resolved_limit = _api_page_limit(
        limit,
        default=settings.api_timeline_default_limit,
        maximum=settings.api_timeline_max_limit,
        field_name="limit",
    )
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).list_timeline(
                game_jobs.ListTimelineQuery(
                    game_id=game_id,
                    after=after,
                    limit=resolved_limit,
                )
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_GAME_TIMELINE_LISTED,
        extra={
            "event_action": LOG_GAME_TIMELINE_LISTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "after": after,
            "limit": resolved_limit,
            "count": len(response.items),
            "next_after": response.next_after,
        },
    )
    return _wire_model(GameTimelineResponse, response)


def get_player_observation(
    game_id: str,
    player_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    manual_token: str,
) -> PlayerObservationResponse:
    """Return a private observation for one authenticated manual player.

    Args:
        game_id: Game id from the public route.
        player_id: Player id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        manual_token: Bearer token supplied by the client.

    Returns:
        Private observation visible to the authenticated player.

    Raises:
        ResourceNotFoundError: If the id is invalid or the game is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_player_observation(
                game_jobs.GetPlayerObservationQuery(
                    game_id=game_id,
                    player_id=player_id,
                    manual_token=manual_token,
                )
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_PRIVATE_OBSERVATION_RETURNED,
        extra={
            "event_action": LOG_PRIVATE_OBSERVATION_RETURNED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
        },
    )
    return _wire_model(PlayerObservationResponse, response)


def submit_player_action(
    game_id: str,
    player_id: str,
    request: PlayerActionRequest,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    manual_token: str,
) -> PlayerActionResponse:
    """Submit one authenticated manual player action.

    Args:
        game_id: Game id from the public route.
        player_id: Player id from the public route.
        request: Validated manual action body.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        manual_token: Bearer token supplied by the client.

    Returns:
        Updated public state and public timeline items caused by the action.

    Raises:
        ResourceNotFoundError: If the id is invalid or the game is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).submit_player_action(
                game_jobs.PlayerActionCommand(
                    game_id=game_id,
                    player_id=player_id,
                    manual_token=manual_token,
                    **request.model_dump(mode="json"),
                )
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_PLAYER_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_PLAYER_ACTION_SUBMITTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "has_target": request.target_id is not None,
            "has_message": bool(request.message),
        },
    )
    return _wire_model(PlayerActionResponse, response)


def _use_cases(session: Session, settings: AppSettings) -> game_jobs.GameService:
    return game_jobs.GameService(_dependencies(session, settings))


def _dependencies(
    session: Session,
    settings: AppSettings,
) -> game_jobs.GameUseCaseDependencies:
    return game_jobs.GameUseCaseDependencies(
        repository=SqlAlchemyGameRepository(session),
        config=build_game_usecase_config(settings),
        game_definitions=build_game_definitions(settings),
        llm_definitions=build_llm_definitions(settings),
        llm_provider_config=build_llm_provider_config(settings),
        telemetry=LoggingTelemetrySink(),
    )


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))


def _create_command(
    request: CreateGameRequest,
    settings: AppSettings,
) -> game_jobs.CreateGameCommand:
    return game_jobs.CreateGameCommand(
        seed=request.seed,
        role_counts=request.role_counts,
        manual_player_id=request.manual_player_id,
        rules=request.rules or settings.game_definitions.rules.local_rules,
        scenario_id=request.scenario_id,
        setup_preset_id=request.setup_preset_id,
        narration_mode=request.narration_mode or settings.game_default_narration_mode,
        character_assignments=request.character_assignments,
        custom_roles=[
            CustomRoleDefinition.model_validate(item.model_dump(mode="json"))
            for item in request.custom_roles
        ],
        custom_characters=[
            CustomCharacterDefinition.model_validate(item.model_dump(mode="json"))
            for item in request.custom_characters
        ],
    )


def _api_page_limit(
    value: int | None,
    *,
    default: int,
    maximum: int,
    field_name: str,
) -> int:
    limit = default if value is None else value
    if limit < MIN_PAGE_LIMIT or limit > maximum:
        raise AppError(
            message_field_must_be_between(field_name, MIN_PAGE_LIMIT, maximum),
            code=ErrorCode.CONFIG_INVALID_VALUE,
            context={field_name: limit, "max_limit": maximum},
        )
    return limit


def _setup_options_response(
    options: game_jobs.GameSetupOptionsResult,
    settings: AppSettings,
) -> GameSetupOptionsResponse:
    role_names = settings.game_role_name_map
    return GameSetupOptionsResponse(
        player_count=options.player_count,
        roles=[
            RoleDefinitionView(
                id=role_id,
                name=str(definition.get("label") or role_names.get(role_id, role_id)),
                faction=str(definition["faction"]),
                abilities=[str(ability) for ability in definition.get("abilities") or []],
                description=str(definition.get("description") or ""),
                difficulty=int(definition.get("difficulty") or 1),
            )
            for role_id, definition in options.roles.items()
        ],
        default_role_counts=options.default_role_counts,
        default_rules=LocalRulesSettings.model_validate(
            options.default_rules.model_dump(mode="json")
        ),
        default_scenario_id=options.default_scenario_id,
        default_setup_preset_id=options.default_setup_preset_id,
        default_narration_mode=options.default_narration_mode,
        abilities=[
            AbilityDefinitionView(
                id=ability_id,
                name=str(definition["label"]),
                description=str(definition["description"]),
                target_policy=str(definition["target_policy"]),
                difficulty=int(definition["difficulty"]),
            )
            for ability_id, definition in options.abilities.items()
        ],
        scenarios=[
            ScenarioDefinitionView(
                id=scenario_id,
                name=str(definition["label"]),
                summary=str(definition["summary"]),
                recommended_setup_preset=cast(
                    str | None,
                    definition.get("recommended_setup_preset"),
                ),
            )
            for scenario_id, definition in options.scenarios.items()
        ],
        setup_presets=[
            SetupPresetDefinitionView(
                id=preset_id,
                name=str(definition["label"]),
                scenario_id=str(definition["scenario_id"]),
                role_counts={
                    str(role_id): int(count)
                    for role_id, count in dict(definition["role_counts"]).items()
                },
            )
            for preset_id, definition in options.setup_presets.items()
        ],
        characters=[
            CharacterDefinitionView(
                id=character_id,
                name=str(definition["name"]),
                age=int(definition["age"]),
                gender=str(definition["gender"]),
                personality=str(definition["personality"]),
                speaking_style=str(definition["speaking_style"]),
                reasoning_style=str(definition["reasoning_style"]),
                risk_tolerance=str(definition["risk_tolerance"]),
            )
            for character_id, definition in options.characters.items()
        ],
    )
