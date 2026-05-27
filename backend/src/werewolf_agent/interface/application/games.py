"""Interface application bridge for game use cases."""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.errors import ResourceNotFoundError
from werewolf_agent.interface.application.repositories import SqlAlchemyGameRunRepository
from werewolf_agent.interface.application.settings import build_game_usecase_settings
from werewolf_agent.interface.shared.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    RulesetResponse,
    StepGameResponse,
)
from werewolf_agent.interface.shared.settings import AppSettings, get_settings
from werewolf_agent.usecase.jobs import (
    CreateGameCommand,
    DummyAgentFactory,
    GameNotFoundError,
    GameUseCaseDependencies,
    GameUseCaseSettings,
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
        return _wire_model(RulesetResponse, get_default_ruleset(settings=self._usecase_settings()))

    def create_game_run(self, request: CreateGameRequest) -> GameResponse:
        """Create and persist one deterministic game."""
        command = CreateGameCommand.model_validate(request.model_dump(mode="json"))
        with session_scope(self.session_factory) as session:
            response = create_game(command, dependencies=self._dependencies(session))
        return _wire_model(GameResponse, response)

    def get_game_run(self, game_id: UUID) -> GameResponse:
        """Return the current public state for one game run."""
        with session_scope(self.session_factory) as session:
            try:
                response = get_game(game_id, repository=SqlAlchemyGameRunRepository(session))
            except GameNotFoundError as exc:
                raise ResourceNotFoundError("Game not found.") from exc
        return _wire_model(GameResponse, response)

    def step_game_run(self, game_id: UUID) -> StepGameResponse:
        """Advance one game run by one deterministic use case step."""
        with session_scope(self.session_factory) as session:
            try:
                response = advance_game(game_id, dependencies=self._dependencies(session))
            except GameNotFoundError as exc:
                raise ResourceNotFoundError("Game not found.") from exc
        return _wire_model(StepGameResponse, response)

    def get_public_events(self, game_id: UUID, *, after: int = 0) -> GameEventsResponse:
        """List public events after a sequence number."""
        with session_scope(self.session_factory) as session:
            try:
                response = list_public_events(
                    game_id,
                    repository=SqlAlchemyGameRunRepository(session),
                    after=after,
                )
            except GameNotFoundError as exc:
                raise ResourceNotFoundError("Game not found.") from exc
        return _wire_model(GameEventsResponse, response)

    def _dependencies(self, session: Session) -> GameUseCaseDependencies:
        return GameUseCaseDependencies(
            repository=SqlAlchemyGameRunRepository(session),
            agent_factory=DummyAgentFactory(),
            rng_factory=random.Random,
            game_id_factory=uuid.uuid4,
            logger=logging.getLogger(__name__),
            settings=self._usecase_settings(),
        )

    def _usecase_settings(self) -> GameUseCaseSettings:
        return build_game_usecase_settings(self.settings)


def default_application(session_factory: SessionFactory) -> GameApplication:
    """Return a game application using process settings."""
    return GameApplication(session_factory=session_factory, settings=get_settings())


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))
