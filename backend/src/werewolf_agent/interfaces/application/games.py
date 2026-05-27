"""Interface application bridge for game use cases."""

from __future__ import annotations

from typing import TypeVar

from django.db import transaction
from pydantic import BaseModel

from werewolf_agent.commons.configuration import AppSettings, get_settings
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    RulesetResponse,
    StepGameResponse,
)
from werewolf_agent.interfaces.application.errors import ResourceNotFoundError
from werewolf_agent.interfaces.application.repositories import DjangoGameRunRepository
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


def default_ruleset() -> RulesetResponse:
    """Return the public MVP ruleset."""
    settings = get_settings()
    ruleset = get_default_ruleset(config=_usecase_config(settings))
    return _ruleset_response(ruleset, settings)


def create_game_run(request: CreateGameRequest) -> GameResponse:
    """Create and persist one deterministic game."""
    command = CreateGameCommand.model_validate(request.model_dump(mode="json"))
    with transaction.atomic():
        response = create_game(command, dependencies=_dependencies())
    return _contract_model(GameResponse, response)


def get_game_run(game_id: str) -> GameResponse:
    """Return the current public state for one game run."""
    try:
        response = get_game(GetGameQuery(game_id=game_id), dependencies=_dependencies())
    except (GameNotFoundError, InvalidGameIdError) as exc:
        raise ResourceNotFoundError("Game not found.") from exc
    return _contract_model(GameResponse, response)


def step_game_run(game_id: str) -> StepGameResponse:
    """Advance one game run by one deterministic use case step."""
    try:
        with transaction.atomic():
            response = advance_game(
                AdvanceGameCommand(game_id=game_id),
                dependencies=_dependencies(),
            )
    except (GameNotFoundError, InvalidGameIdError) as exc:
        raise ResourceNotFoundError("Game not found.") from exc
    return _contract_model(StepGameResponse, response)


def get_public_events(game_id: str, *, after: int = 0) -> GameEventsResponse:
    """List public events after a sequence number."""
    try:
        response = list_public_events(
            ListPublicEventsQuery(game_id=game_id, after=after),
            dependencies=_dependencies(),
        )
    except (GameNotFoundError, InvalidGameIdError) as exc:
        raise ResourceNotFoundError("Game not found.") from exc
    return _contract_model(GameEventsResponse, response)


def _dependencies() -> GameUseCaseDependencies:
    return GameUseCaseDependencies(
        repository=DjangoGameRunRepository(),
        config=_usecase_config(get_settings()),
    )


def _usecase_config(settings: AppSettings) -> GameUseCaseConfig:
    return GameUseCaseConfig(
        min_players=settings.game_min_players,
        max_players=settings.game_max_players,
        default_player_count=settings.game_default_player_count,
        supported_agent_type=settings.game_supported_agent_type,
        default_ruleset_id=settings.game_default_ruleset_id,
    )


def _contract_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))


def _ruleset_response(ruleset: RulesetResult, settings: AppSettings) -> RulesetResponse:
    return RulesetResponse(
        id=ruleset.id,
        name=settings.game_default_ruleset_name,
        description=_ruleset_description(settings),
        player_count=ruleset.player_count,
        roles=[{"id": role_id, "name": _role_name(role_id)} for role_id in ruleset.roles],
        phases=[{"id": phase_id, "name": _phase_name(phase_id)} for phase_id in ruleset.phases],
        agent_types=[
            {
                "id": agent_type,
                "name": settings.game_supported_agent_name,
            }
            for agent_type in ruleset.agent_types
        ],
    )


def _ruleset_description(settings: AppSettings) -> str:
    return (
        f"{settings.game_min_players}〜{settings.game_max_players}"
        "人向けの最小同期 API ルールセットです。"
    )


def _role_name(role_id: str) -> str:
    return {
        "villager": "村人",
        "werewolf": "人狼",
        "seer": "占い師",
        "knight": "騎士",
    }[role_id]


def _phase_name(phase_id: str) -> str:
    return {
        "night": "夜",
        "day_discussion": "昼チャット",
        "voting": "投票",
        "finished": "終了",
    }[phase_id]
