"""Stateless interface application bridge for game use cases."""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.commons.shared.messages import (
    LOG_GAME_EVENTS_LISTED,
    LOG_GAME_RUN_CREATED,
    LOG_GAME_RUN_STEPPED,
    LOG_GAME_RUNS_LISTED,
    LOG_GAME_TURNS_LISTED,
    LOG_PLAYER_ACTION_SUBMITTED,
    LOG_PRIVATE_OBSERVATION_RETURNED,
    MESSAGE_GAME_NOT_FOUND,
)
from werewolf_agent.contracts import GameNotFoundError, InvalidGameIdError, ResourceNotFoundError
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
from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.repositories import SqlAlchemyGameRunRepository
from werewolf_agent.interface.application.settings import (
    build_game_usecase_config,
    build_llm_provider_config,
)

TModel = TypeVar("TModel", bound=BaseModel)
logger = logging.getLogger(__name__)


def get_default_ruleset(*, settings: AppSettings) -> RulesetResponse:
    """Return the public ruleset.

    Args:
        settings: Loaded application settings.

    Returns:
        Wire schema containing ruleset metadata and display names.
    """
    ruleset = game_jobs.get_default_ruleset(config=build_game_usecase_config(settings))
    return _ruleset_response(ruleset, settings)


def create_game_run(
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
    command = game_jobs.CreateGameRunCommand.model_validate(request.model_dump(mode="json"))
    with session_scope(session_factory) as session:
        response = game_jobs.create_game_run(command, dependencies=_dependencies(session, settings))
    logger.info(
        LOG_GAME_RUN_CREATED,
        extra={"game_id": response.game_id, "player_count": request.resolved_player_count},
    )
    return _wire_model(GameResponse, response)


def get_game_run(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> GameResponse:
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
            response = game_jobs.get_game_run(
                game_jobs.GetGameRunQuery(game_id=game_id),
                dependencies=_dependencies(session, settings),
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    return _wire_model(GameResponse, response)


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
        response = game_jobs.list_game_runs(
            game_jobs.ListGameRunsQuery(status=status, limit=limit, offset=offset),
            dependencies=_dependencies(session, settings),
        )
    logger.debug(
        LOG_GAME_RUNS_LISTED,
        extra={"status": status, "limit": limit, "offset": offset, "count": len(response.runs)},
    )
    return _wire_model(GameRunsResponse, response)


def advance_game_run(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> StepGameResponse:
    """Advance one game run by one deterministic use case step.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.

    Returns:
        Updated public state and emitted public events.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.
    """
    with session_scope(session_factory) as session:
        try:
            response = game_jobs.advance_game_run(
                game_jobs.AdvanceGameRunCommand(game_id=game_id),
                dependencies=_dependencies(session, settings),
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_GAME_RUN_STEPPED,
        extra={
            "game_id": response.game_id,
            "status": response.status,
            "version": response.state.get("version"),
            "event_count": len(response.events),
        },
    )
    return _wire_model(StepGameResponse, response)


def list_public_game_events(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    after: int = 0,
    limit: int = 100,
) -> GameEventsResponse:
    """List public events after a sequence number.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        after: Exclusive sequence cursor.
        limit: Maximum number of events to return.

    Returns:
        Public events and the next sequence cursor.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.
    """
    with session_scope(session_factory) as session:
        try:
            response = game_jobs.list_public_game_events(
                game_jobs.ListPublicGameEventsQuery(game_id=game_id, after=after, limit=limit),
                dependencies=_dependencies(session, settings),
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_GAME_EVENTS_LISTED,
        extra={
            "game_id": game_id,
            "after": after,
            "limit": limit,
            "count": len(response.events),
            "next_after": response.next_after,
        },
    )
    return _wire_model(GameEventsResponse, response)


def list_public_game_turns(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    after: int = 0,
    limit: int = 100,
) -> GameTurnsResponse:
    """List public timeline turns after a sequence number.

    Args:
        game_id: Game id from the public route.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        after: Exclusive sequence cursor.
        limit: Maximum number of turn records to return.

    Returns:
        Public timeline records and the next sequence cursor.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.
    """
    with session_scope(session_factory) as session:
        try:
            response = game_jobs.list_public_game_turns(
                game_jobs.ListPublicGameTurnsQuery(game_id=game_id, after=after, limit=limit),
                dependencies=_dependencies(session, settings),
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_GAME_TURNS_LISTED,
        extra={
            "game_id": game_id,
            "after": after,
            "limit": limit,
            "count": len(response.turns),
            "next_after": response.next_after,
        },
    )
    return _wire_model(GameTurnsResponse, response)


def get_player_observation(
    game_id: str,
    player_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    control_token: str,
) -> PrivateObservationResponse:
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
            response = game_jobs.get_player_observation(
                game_jobs.GetPlayerObservationQuery(
                    game_id=game_id,
                    player_id=player_id,
                    control_token=control_token,
                ),
                dependencies=_dependencies(session, settings),
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.debug(
        LOG_PRIVATE_OBSERVATION_RETURNED,
        extra={"game_id": game_id, "player_id": player_id},
    )
    return _wire_model(PrivateObservationResponse, response)


def submit_player_action(
    game_id: str,
    player_id: str,
    request: SubmitPlayerActionRequest,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
    control_token: str,
) -> SubmitPlayerActionResponse:
    """Submit one authenticated manual player action.

    Args:
        game_id: Game id from the public route.
        player_id: Player id from the public route.
        request: Validated manual action body.
        session_factory: SQLAlchemy session factory for one transaction.
        settings: Loaded application settings.
        control_token: Bearer token supplied by the client.

    Returns:
        Updated public state and public events caused by the action.

    Raises:
        ResourceNotFoundError: If the id is invalid or the run is absent.
    """
    with session_scope(session_factory) as session:
        try:
            response = game_jobs.submit_player_action(
                game_jobs.SubmitPlayerActionCommand(
                    game_id=game_id,
                    player_id=player_id,
                    control_token=control_token,
                    **request.model_dump(mode="json"),
                ),
                dependencies=_dependencies(session, settings),
            )
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
    logger.info(
        LOG_PLAYER_ACTION_SUBMITTED,
        extra={"game_id": game_id, "player_id": player_id, "action_type": request.type},
    )
    return _wire_model(SubmitPlayerActionResponse, response)


def _dependencies(
    session: Session,
    settings: AppSettings,
) -> game_jobs.GameUseCaseDependencies:
    return game_jobs.GameUseCaseDependencies(
        repository=SqlAlchemyGameRunRepository(session),
        config=build_game_usecase_config(settings),
        llm_provider_config=build_llm_provider_config(settings),
    )


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))


def _ruleset_response(ruleset: game_jobs.RulesetResult, settings: AppSettings) -> RulesetResponse:
    role_names = settings.game_role_name_map
    phase_names = settings.game_phase_name_map
    return RulesetResponse(
        id=ruleset.id,
        name=settings.game_default_ruleset_name,
        description=_ruleset_description(settings),
        player_count=ruleset.player_count,
        roles=[
            {"id": role_id, "name": role_names.get(role_id, role_id)} for role_id in ruleset.roles
        ],
        phases=[
            {"id": phase_id, "name": phase_names.get(phase_id, phase_id)}
            for phase_id in ruleset.phases
        ],
        agent_types=[
            {
                "id": agent_type,
                "name": (
                    "Human Player" if agent_type == "human" else settings.game_supported_agent_name
                ),
            }
            for agent_type in ruleset.agent_types
        ],
    )


def _ruleset_description(settings: AppSettings) -> str:
    return settings.game_ruleset_description_template.format(
        min_players=settings.game_min_players,
        max_players=settings.game_max_players,
        default_player_count=settings.game_default_player_count,
    )
