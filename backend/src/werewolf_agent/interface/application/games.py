"""Interface application bridge for game use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from werewolf_agent.commons.shared.messages import MESSAGE_GAME_NOT_FOUND
from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.errors import ResourceNotFoundError
from werewolf_agent.interface.application.repositories import SqlAlchemyGameRunRepository
from werewolf_agent.interface.application.settings import build_game_usecase_config
from werewolf_agent.interface.shared.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    RulesetResponse,
    StepGameResponse,
)
from werewolf_agent.interface.shared.settings import AppSettings, get_settings
from werewolf_agent.usecase.jobs import (
    AdvanceGameCommand,
    CreateGameCommand,
    GameNotFoundError,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameQuery,
    InvalidGameIdError,
    ListPublicEventsQuery,
    RulesetResult,
    advance_game,
    create_game,
    get_default_ruleset,
    get_game,
    list_public_events,
)

TModel = TypeVar("TModel", bound=BaseModel)


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
        return _wire_model(StepGameResponse, response)

    def get_public_events(self, game_id: str, *, after: int = 0) -> GameEventsResponse:
        """List public events after a sequence number."""
        with session_scope(self.session_factory) as session:
            try:
                response = list_public_events(
                    ListPublicEventsQuery(game_id=game_id, after=after),
                    dependencies=self._dependencies(session),
                )
            except (GameNotFoundError, InvalidGameIdError) as exc:
                raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc
        return _wire_model(GameEventsResponse, response)

    def _dependencies(self, session: Session) -> GameUseCaseDependencies:
        return GameUseCaseDependencies(
            repository=SqlAlchemyGameRunRepository(session),
            config=self._usecase_config(),
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
            {"id": agent_type, "name": settings.game_supported_agent_name}
            for agent_type in ruleset.agent_types
        ],
    )


def _ruleset_description(settings: AppSettings) -> str:
    return settings.game_ruleset_description_template.format(
        min_players=settings.game_min_players,
        max_players=settings.game_max_players,
        default_player_count=settings.game_default_player_count,
    )
