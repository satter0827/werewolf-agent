"""Thin Django service adapters for game use cases."""

from __future__ import annotations

import logging
import random
import uuid
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import NotFound

from werewolf_agent.interfaces.api.games.repositories import DjangoGameRunRepository
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
    GameEventsResponse,
    GameResponse,
    GameUseCaseSettings,
    RulesetResponse,
    StepGameResponse,
)


def default_ruleset() -> RulesetResponse:
    """Return the public MVP ruleset."""
    return get_default_ruleset(settings=_settings())


def create_game_run(command: CreateGameCommand) -> GameResponse:
    """Create and persist one deterministic game."""
    with transaction.atomic():
        return create_game(command, dependencies=_dependencies())


def get_game_run(game_id: UUID) -> GameResponse:
    """Return the current public state for one game run."""
    try:
        return get_game(game_id, repository=DjangoGameRunRepository())
    except GameNotFoundError as exc:
        raise NotFound("Game not found.") from exc


def step_game_run(game_id: UUID) -> StepGameResponse:
    """Advance one game run by one deterministic use case step."""
    try:
        with transaction.atomic():
            return advance_game(game_id, dependencies=_dependencies())
    except GameNotFoundError as exc:
        raise NotFound("Game not found.") from exc


def get_public_events(game_id: UUID, *, after: int = 0) -> GameEventsResponse:
    """List public events after a sequence number."""
    try:
        return list_public_events(
            game_id,
            repository=DjangoGameRunRepository(),
            after=after,
        )
    except GameNotFoundError as exc:
        raise NotFound("Game not found.") from exc


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
    return GameUseCaseSettings()
