"""Interface application bridge for game use cases."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

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
from werewolf_agent.interface.application.agents import build_agent_factory
from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.errors import ResourceNotFoundError
from werewolf_agent.interface.application.repositories import SqlAlchemyGameRunRepository
from werewolf_agent.interface.application.settings import build_game_usecase_config
from werewolf_agent.interface.shared.schemas import (
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
from werewolf_agent.interface.shared.settings import AppSettings, get_settings
from werewolf_agent.usecase.jobs import (
    AdvanceGameCommand,
    CreateGameCommand,
    GameNotFoundError,
    GameStatus,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameQuery,
    GetPrivateObservationQuery,
    InvalidGameIdError,
    ListGamesQuery,
    ListGameTurnsQuery,
    ListPublicEventsQuery,
    RulesetResult,
    SubmitPlayerActionCommand,
    advance_game,
    create_game,
    get_default_ruleset,
    get_game,
    get_private_observation,
    list_game_turns,
    list_games,
    list_public_events,
    submit_player_action,
)

TModel = TypeVar("TModel", bound=BaseModel)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameApplication:
    """Use case adapter with injected settings and persistence."""

    session_factory: SessionFactory
    settings: AppSettings

    def default_ruleset(self) -> RulesetResponse:
        """Return the public ruleset."""
        ruleset = get_default_ruleset(config=self._usecase_config())
        return _ruleset_response(ruleset, self.settings)

    def create_game_run(self, request: CreateGameRequest) -> GameResponse:
        """Create and persist one deterministic game."""
        command = CreateGameCommand.model_validate(request.model_dump(mode="json"))
        with session_scope(self.session_factory) as session:
            response = create_game(command, dependencies=self._dependencies(session))
        logger.info(
            LOG_GAME_RUN_CREATED,
            extra={"game_id": response.game_id, "player_count": request.resolved_player_count},
        )
        return _wire_model(GameResponse, response)

    def get_game_run(self, game_id: str) -> GameResponse:
        """Return the current public state for one game run."""
        with session_scope(self.session_factory) as session:
            try:
                response = get_game(
                    GetGameQuery(game_id=game_id),
                    dependencies=self._dependencies(session),
                )
            except (GameNotFoundError, InvalidGameIdError) as exc:
                raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
        return _wire_model(GameResponse, response)

    def list_game_runs(
        self,
        *,
        status: GameStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameRunsResponse:
        """Return public game run summaries."""
        with session_scope(self.session_factory) as session:
            response = list_games(
                ListGamesQuery(status=status, limit=limit, offset=offset),
                dependencies=self._dependencies(session),
            )
        logger.debug(
            LOG_GAME_RUNS_LISTED,
            extra={"status": status, "limit": limit, "offset": offset, "count": len(response.runs)},
        )
        return _wire_model(GameRunsResponse, response)

    def step_game_run(self, game_id: str) -> StepGameResponse:
        """Advance one game run by one deterministic use case step."""
        with session_scope(self.session_factory) as session:
            try:
                response = advance_game(
                    AdvanceGameCommand(game_id=game_id),
                    dependencies=self._dependencies(session),
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

    def get_public_events(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameEventsResponse:
        """List public events after a sequence number."""
        with session_scope(self.session_factory) as session:
            try:
                response = list_public_events(
                    ListPublicEventsQuery(game_id=game_id, after=after, limit=limit),
                    dependencies=self._dependencies(session),
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

    def get_public_turns(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTurnsResponse:
        """List public timeline turns after a sequence number."""
        with session_scope(self.session_factory) as session:
            try:
                response = list_game_turns(
                    ListGameTurnsQuery(game_id=game_id, after=after, limit=limit),
                    dependencies=self._dependencies(session),
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

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        """Return a private observation for one authenticated manual player."""
        with session_scope(self.session_factory) as session:
            try:
                response = get_private_observation(
                    GetPrivateObservationQuery(
                        game_id=game_id,
                        player_id=player_id,
                        control_token=control_token,
                    ),
                    dependencies=self._dependencies(session),
                )
            except (GameNotFoundError, InvalidGameIdError) as exc:
                raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
        logger.debug(
            LOG_PRIVATE_OBSERVATION_RETURNED,
            extra={"game_id": game_id, "player_id": player_id},
        )
        return _wire_model(PrivateObservationResponse, response)

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: SubmitPlayerActionRequest,
        *,
        control_token: str,
    ) -> SubmitPlayerActionResponse:
        """Submit one authenticated manual player action."""
        with session_scope(self.session_factory) as session:
            try:
                response = submit_player_action(
                    SubmitPlayerActionCommand(
                        game_id=game_id,
                        player_id=player_id,
                        control_token=control_token,
                        **request.model_dump(mode="json"),
                    ),
                    dependencies=self._dependencies(session),
                )
            except (GameNotFoundError, InvalidGameIdError) as exc:
                raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
        logger.info(
            LOG_PLAYER_ACTION_SUBMITTED,
            extra={"game_id": game_id, "player_id": player_id, "action_type": request.type},
        )
        return _wire_model(SubmitPlayerActionResponse, response)

    def _dependencies(self, session: Session) -> GameUseCaseDependencies:
        return GameUseCaseDependencies(
            repository=SqlAlchemyGameRunRepository(session),
            config=self._usecase_config(),
            agent_factory=build_agent_factory(self.settings),
        )

    def _usecase_config(self) -> GameUseCaseConfig:
        return build_game_usecase_config(self.settings)


def default_application(session_factory: SessionFactory) -> GameApplication:
    """Return a game application using process settings."""
    return GameApplication(session_factory=session_factory, settings=get_settings())


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))


def _ruleset_response(ruleset: RulesetResult, settings: AppSettings) -> RulesetResponse:
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
