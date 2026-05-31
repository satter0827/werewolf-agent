"""Stateless interface application bridge for game use cases."""

from __future__ import annotations

import logging
from typing import TypeVar, cast

from pydantic import BaseModel
from sqlalchemy.orm import Session

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.commons.shared.messages import (
    LOG_GAME_RUN_CREATED,
    LOG_GAME_RUN_STEPPED,
    LOG_GAME_RUNS_LISTED,
    LOG_GAME_TIMELINE_LISTED,
    LOG_PLAYER_ACTION_SUBMITTED,
    LOG_PRIVATE_OBSERVATION_RETURNED,
    MESSAGE_GAME_NOT_FOUND,
)
from werewolf_agent.contracts import (
    AppError,
    GameNotFoundError,
    InvalidGameIdError,
    ResourceNotFoundError,
)
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    AdvanceGameRunResponse,
    AdvanceUntilInputResponse,
    CreateGameRequest,
    GameRevealResponse,
    GameRunResponse,
    GameRunsResponse,
    GameTimelineResponse,
    LocalRulesSettings,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
    RoleDefinitionView,
    RulesetResponse,
)
from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.repositories import SqlAlchemyGameRunRepository
from werewolf_agent.interface.application.settings import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
    build_llm_provider_config,
)
from werewolf_agent.interface.application.telemetry import LoggingTelemetrySink
from werewolf_agent.interface.runtime import AppSettings

TModel = TypeVar("TModel", bound=BaseModel)
logger = logging.getLogger(__name__)


def get_default_ruleset(*, settings: AppSettings) -> RulesetResponse:
    """Return the public ruleset.

    Args:
        settings: Loaded application settings.

    Returns:
        Wire schema containing ruleset metadata and display names.

    """
    ruleset = _ruleset_use_cases(settings).get_default_ruleset()
    return _ruleset_response(ruleset, settings)


def create_game_run(
    request: CreateGameRequest,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameRunResponse:
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
        response = _use_cases(session, settings).create_game_run(command)
    logger.info(
        LOG_GAME_RUN_CREATED,
        extra={
            "event_action": LOG_GAME_RUN_CREATED,
            "event_outcome": "success",
            "game_id": response.game_id,
            "player_count": request.player_count,
        },
    )
    return _wire_model(GameRunResponse, response)


def get_game_run(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameRunResponse:
    """Return the current public state for one game run.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.

    Returns:
        Public game response.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_game_run(
                game_jobs.GetGameRunQuery(game_id=game_id)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    return _wire_model(GameRunResponse, response)


def get_game_reveal(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameRevealResponse:
    """Return full observer-only game information when reveal API is enabled."""
    if not settings.reveal_api_enabled:
        raise AppError("Reveal API is disabled.", code=ErrorCode.AUTHORIZATION_FAILED)
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_game_reveal(
                game_jobs.GetGameRevealQuery(game_id=game_id)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    return _wire_model(GameRevealResponse, response)


def list_game_runs(
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    status: game_jobs.GameStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> GameRunsResponse:
    """Return public game run summaries.

    Args:
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        status: Optional public run status filter.
        limit: Maximum number of rows to return.
        offset: Result offset for pagination.

    Returns:
        Public run summaries and pagination metadata.

    """
    with session_scope(session_factory) as session:
        response = _use_cases(session, settings).list_game_runs(
            game_jobs.ListGameRunsQuery(status=status, limit=limit, offset=offset)
        )
    logger.debug(
        LOG_GAME_RUNS_LISTED,
        extra={
            "event_action": LOG_GAME_RUNS_LISTED,
            "event_outcome": "success",
            "game_status": status,
            "limit": limit,
            "offset": offset,
            "count": len(response.runs),
        },
    )
    return _wire_model(GameRunsResponse, response)


def advance_game_run(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> AdvanceGameRunResponse:
    """Advance one game run by one deterministic use case step.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.

    Returns:
        Updated public state and emitted public timeline items.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).advance_game_run(
                game_jobs.AdvanceGameRunCommand(game_id=game_id)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_GAME_RUN_STEPPED,
        extra={
            "event_action": LOG_GAME_RUN_STEPPED,
            "event_outcome": "success",
            "game_id": response.game_id,
            "game_status": response.status,
            "game_phase": response.state.get("phase"),
            "game_day": response.state.get("day"),
            "game_version": response.state.get("version"),
            "event_count": len(response.timeline),
        },
    )
    return _wire_model(AdvanceGameRunResponse, response)


def advance_until_input(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    max_steps: int | None = None,
) -> AdvanceUntilInputResponse:
    """Advance one game until manual input, completion, or step limit."""
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).advance_until_input(
                game_jobs.AdvanceUntilInputCommand(
                    game_id=game_id,
                    max_steps=max_steps or settings.game_advance_until_input_max_steps,
                )
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_GAME_RUN_STEPPED,
        extra={
            "event_action": LOG_GAME_RUN_STEPPED,
            "event_outcome": "success",
            "game_id": response.game_id,
            "game_status": response.status,
            "game_phase": response.state.get("phase"),
            "game_day": response.state.get("day"),
            "game_version": response.state.get("version"),
            "event_count": len(response.timeline),
            "stop_reason": response.stop_reason,
            "steps": response.steps,
        },
    )
    return _wire_model(AdvanceUntilInputResponse, response)


def get_game_timeline(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    after: int = 0,
    limit: int = 100,
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
        ResourceNotFoundError: If the id is invalid or the run is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_game_timeline(
                game_jobs.GetGameTimelineQuery(game_id=game_id, after=after, limit=limit)
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_GAME_TIMELINE_LISTED,
        extra={
            "event_action": LOG_GAME_TIMELINE_LISTED,
            "event_outcome": "success",
            "game_id": game_id,
            "after": after,
            "limit": limit,
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
    control_token: str,
) -> PlayerObservationResponse:
    """Return a private observation for one authenticated manual player.

    Args:
        game_id: Game id from the public route.
        player_id: Player id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        control_token: Bearer token supplied by the client.

    Returns:
        Private observation visible to the authenticated player.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).get_player_observation(
                game_jobs.GetPlayerObservationQuery(
                    game_id=game_id,
                    player_id=player_id,
                    control_token=control_token,
                )
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_PRIVATE_OBSERVATION_RETURNED,
        extra={
            "event_action": LOG_PRIVATE_OBSERVATION_RETURNED,
            "event_outcome": "success",
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
    control_token: str,
) -> PlayerActionResponse:
    """Submit one authenticated manual player action.

    Args:
        game_id: Game id from the public route.
        player_id: Player id from the public route.
        request: Validated manual action body.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        control_token: Bearer token supplied by the client.

    Returns:
        Updated public state and public timeline items caused by the action.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.

    """
    with session_scope(session_factory) as session:
        try:
            response = _use_cases(session, settings).submit_player_action(
                game_jobs.PlayerActionCommand(
                    game_id=game_id,
                    player_id=player_id,
                    control_token=control_token,
                    **request.model_dump(mode="json"),
                )
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_PLAYER_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_PLAYER_ACTION_SUBMITTED,
            "event_outcome": "success",
            "game_id": game_id,
            "has_target": request.target_id is not None,
            "has_message": bool(request.message),
        },
    )
    return _wire_model(PlayerActionResponse, response)


def _use_cases(session: Session, settings: AppSettings) -> game_jobs.GameUseCases:
    return game_jobs.GameUseCases(_dependencies(session, settings))


def _ruleset_use_cases(settings: AppSettings) -> game_jobs.GameUseCases:
    return game_jobs.GameUseCases(
        game_jobs.GameUseCaseDependencies(
            repository=cast(game_jobs.GameRepository, object()),
            config=build_game_usecase_config(settings),
            game_definitions=build_game_definitions(settings),
            llm_definitions=build_llm_definitions(settings),
            llm_provider_config=build_llm_provider_config(settings),
            telemetry=LoggingTelemetrySink(),
        )
    )


def _dependencies(
    session: Session,
    settings: AppSettings,
) -> game_jobs.GameUseCaseDependencies:
    return game_jobs.GameUseCaseDependencies(
        repository=SqlAlchemyGameRunRepository(session),
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
        human_player_id=request.human_player_id,
        rules=request.rules or settings.game_definitions.rules.local_rules,
    )


def _ruleset_response(ruleset: game_jobs.RulesetResult, settings: AppSettings) -> RulesetResponse:
    role_names = settings.game_role_name_map
    return RulesetResponse(
        player_count=ruleset.player_count,
        roles=[
            RoleDefinitionView(
                id=role_id,
                name=role_names.get(role_id, role_id),
                faction=str(definition["faction"]),
                abilities=[str(ability) for ability in definition.get("abilities") or []],
            )
            for role_id, definition in ruleset.roles.items()
        ],
        default_role_counts=ruleset.default_role_counts,
        default_rules=LocalRulesSettings.model_validate(
            ruleset.default_rules.model_dump(mode="json")
        ),
    )
