"""Interface application bridge for game use cases."""

from __future__ import annotations

import logging
import random
import uuid
from typing import TypeVar
from uuid import UUID

from django.db import transaction
from pydantic import BaseModel

from werewolf_agent.configuration import build_game_usecase_settings, get_settings
from werewolf_agent.contracts.api import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    RulesetResponse,
    StepGameResponse,
)
from werewolf_agent.interfaces.application.errors import ResourceNotFoundError
from werewolf_agent.interfaces.application.repositories import DjangoGameRunRepository
from werewolf_agent.usecase.agents import DummyAgentFactory
from werewolf_agent.usecase.games import (
    GameNotFoundError,
    GameUseCaseDependencies,
    advance_game,
    create_game,
    get_default_ruleset,
    get_game,
    list_public_events,
)
from werewolf_agent.usecase.models import (
    CreateGameCommand,
    GameUseCaseSettings,
)

TModel = TypeVar("TModel", bound=BaseModel)


def default_ruleset() -> RulesetResponse:
    """Return the public MVP ruleset."""
    return _contract_model(RulesetResponse, get_default_ruleset(settings=_settings()))


def create_game_run(request: CreateGameRequest) -> GameResponse:
    """Create and persist one deterministic game."""
    command = CreateGameCommand.model_validate(request.model_dump(mode="json"))
    with transaction.atomic():
        response = create_game(command, dependencies=_dependencies())
    return _contract_model(GameResponse, response)


def get_game_run(game_id: UUID) -> GameResponse:
    """Return the current public state for one game run."""
    try:
        response = get_game(game_id, repository=DjangoGameRunRepository())
    except GameNotFoundError as exc:
        raise ResourceNotFoundError("Game not found.") from exc
    return _contract_model(GameResponse, response)


def step_game_run(game_id: UUID) -> StepGameResponse:
    """Advance one game run by one deterministic use case step."""
    try:
        with transaction.atomic():
            response = advance_game(game_id, dependencies=_dependencies())
    except GameNotFoundError as exc:
        raise ResourceNotFoundError("Game not found.") from exc
    return _contract_model(StepGameResponse, response)


def get_public_events(game_id: UUID, *, after: int = 0) -> GameEventsResponse:
    """List public events after a sequence number."""
    try:
        response = list_public_events(
            game_id,
            repository=DjangoGameRunRepository(),
            after=after,
        )
    except GameNotFoundError as exc:
        raise ResourceNotFoundError("Game not found.") from exc
    return _contract_model(GameEventsResponse, response)


def _dependencies() -> GameUseCaseDependencies:
    return GameUseCaseDependencies(
        repository=DjangoGameRunRepository(),
        agent_factory=DummyAgentFactory(),
        rng_factory=random.Random,
        game_id_factory=uuid.uuid4,
        logger=logging.getLogger(__name__),
        settings=_settings(),
    )


def _settings() -> GameUseCaseSettings:
    return build_game_usecase_settings(get_settings())


def _contract_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))
