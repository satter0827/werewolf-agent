"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from werewolf_agent.application.constants import (
    DEFAULT_NARRATION_MODE,
    MIN_PAGE_LIMIT,
    NARRATION_MODE_CHOICES,
    NarrationMode,
)
from werewolf_agent.application.definitions import (
    GameDefinitions,
    NarrationEventDefinition,
    NarrationProfileDefinition,
    PlayerRoster,
)
from werewolf_agent.application.domain_codec import action_from_data, game_state_from_data
from werewolf_agent.application.errors import (
    AppError,
    ErrorCode,
    GameError,
    InvalidGameIdError,
)
from werewolf_agent.application.messages import (
    MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_CHARACTER_IDS,
    MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_GENERATED_PLAYER_IDS,
    MESSAGE_GAME_ID_MUST_BE_VALID_UUID,
    MESSAGE_PLAYER_AUTHENTICATION_REQUIRED,
    MESSAGE_PLAYER_IS_NOT_MANUAL,
    MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS,
    message_field_must_be_between,
    message_player_count_between,
    message_unsupported_action_type,
)
from werewolf_agent.application.models import (
    CreateGameCommand,
    GameApplicationConfig,
    GameRevealAction,
    PlayerActionCommand,
    StoredGame,
)
from werewolf_agent.application.players import (
    SelectedPlayerProfile,
    select_players,
)
from werewolf_agent.application.randomness import runtime_seed
from werewolf_agent.application.rules import rule_definition_from_state
from werewolf_agent.application.validation import (
    generated_player_id,
    generated_player_ids,
    generated_player_name,
)
from werewolf_agent.domain import (
    Action,
    Game,
    GameState,
    RuleRegistry,
)


@dataclass(frozen=True)
class RequestedPlayer:
    """Resolved player seat requested for a game."""

    id: str
    name: str
    agent_type: str


def _page_limit(
    value: int | None,
    *,
    default: int,
    maximum: int,
    field_name: str,
) -> int:
    limit = default if value is None else value
    if limit < MIN_PAGE_LIMIT or limit > maximum:
        raise GameError(
            message_field_must_be_between(field_name, MIN_PAGE_LIMIT, maximum),
            context={field_name: limit, "max_limit": maximum},
        )
    return limit


def _select_player_profiles(
    roster: PlayerRoster,
    *,
    player_count: int,
    seed: int | None,
    character_assignments: Mapping[str, str],
) -> list[SelectedPlayerProfile]:
    if not character_assignments:
        return select_players(roster, player_count=player_count, seed=seed)

    valid_player_ids = generated_player_ids(player_count)
    unknown_players = sorted(set(character_assignments) - valid_player_ids)
    if unknown_players:
        raise GameError(
            MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_GENERATED_PLAYER_IDS,
            context={"player_ids": unknown_players},
        )

    unknown_profiles = sorted(set(character_assignments.values()) - set(roster.players))
    if unknown_profiles:
        raise GameError(
            MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_CHARACTER_IDS,
            context={"character_ids": unknown_profiles},
        )

    assigned_profile_ids = set(character_assignments.values())
    remaining = [
        (profile_id, profile)
        for profile_id, profile in sorted(roster.players.items())
        if profile_id not in assigned_profile_ids
    ]
    missing_count = player_count - len(character_assignments)
    if missing_count > len(remaining):
        raise GameError(
            MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS,
            context={"player_count": player_count, "roster_count": len(roster.players)},
        )
    rng = random.Random(seed)
    sampled = {
        generated_player_id(index): SelectedPlayerProfile(profile_id=profile_id, profile=profile)
        for index, (profile_id, profile) in enumerate(
            rng.sample(remaining, missing_count),
            start=1,
        )
    }
    selected: list[SelectedPlayerProfile] = []
    fallback_index = 1
    for index in range(1, player_count + 1):
        player_id = generated_player_id(index)
        assigned_id = character_assignments.get(player_id)
        if assigned_id is not None:
            selected.append(
                SelectedPlayerProfile(
                    profile_id=assigned_id,
                    profile=roster.players[assigned_id],
                )
            )
            continue
        while generated_player_id(fallback_index) not in sampled:
            fallback_index += 1
        selected.append(sampled[generated_player_id(fallback_index)])
        fallback_index += 1
    return selected


def _narration_profile(
    config: Mapping[str, object],
    definitions: GameDefinitions,
) -> NarrationProfileDefinition | None:
    setup_value = config.get("setup_document")
    if isinstance(setup_value, Mapping):
        theme_value = setup_value.get("theme")
        if isinstance(theme_value, Mapping):
            narration_value = theme_value.get("narration")
            if isinstance(narration_value, Mapping):
                return NarrationProfileDefinition(
                    events={
                        str(event_type): NarrationEventDefinition(
                            templates=tuple(str(item) for item in templates)
                        )
                        for event_type, templates in narration_value.items()
                        if isinstance(templates, (list, tuple))
                    }
                )
    profile_id = _config_text(config, "narration_profile")
    if profile_id is None:
        return None
    return definitions.catalog.narration_profiles.get(profile_id)


def _config_text(config: Mapping[str, object], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _setup_theme(config: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return the persisted public theme projection for one game."""
    setup = config.get("setup_document")
    if not isinstance(setup, Mapping):
        return None
    theme = setup.get("theme")
    return theme if isinstance(theme, Mapping) else None


def _narration_mode(config: Mapping[str, object]) -> NarrationMode:
    value = _config_text(config, "narration_mode")
    if value in NARRATION_MODE_CHOICES:
        return cast(NarrationMode, value)
    return DEFAULT_NARRATION_MODE


def _player_faction(snapshot: GameState, role: str | None) -> str:
    if role is None:
        return ""
    return snapshot.config.roles.faction_for_role(role)


def _reveal_action(action: Action) -> GameRevealAction:
    return GameRevealAction(
        player_id=action.player_id,
        type=action.type.value,
        target_id=action.target_id,
        message=action.message,
    )


def _parse_game_id(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidGameIdError(MESSAGE_GAME_ID_MUST_BE_VALID_UUID) from exc


def _action_from_command(command: PlayerActionCommand) -> Action:
    try:
        return action_from_data(
            {
                "player_id": command.player_id,
                "type": command.type,
                "target_id": command.target_id,
                "message": command.message,
                "reason": command.reason,
            }
        )
    except ValueError as exc:
        raise GameError(
            message_unsupported_action_type(command.type),
            context={"action_type": command.type},
        ) from exc


def _restore_game(run: StoredGame) -> Game:
    if run.config.get("engine_schema_version") != 1:
        raise GameError(
            "このゲームは現在の設定形式に対応していません。新しいゲームを作成してください。",
            context={"engine_schema_version": run.config.get("engine_schema_version")},
        )
    state = game_state_from_data({**run.private_state, "pending_actions": run.pending_actions})
    composition_value = run.config.get("rule_composition")
    composition = composition_value if isinstance(composition_value, Mapping) else {}
    rules = RuleRegistry.standard().build(rule_definition_from_state(state, composition))
    return Game.restore(state, rules=rules)


def _requested_player_configs(
    command: CreateGameCommand,
    config: GameApplicationConfig,
) -> list[RequestedPlayer]:
    player_count = command.player_count
    if player_count < config.min_players or player_count > config.max_players:
        raise GameError(message_player_count_between(config.min_players, config.max_players))
    return [
        RequestedPlayer(
            id=generated_player_id(index),
            name=generated_player_name(index),
            agent_type=(
                "manual"
                if generated_player_id(index) == command.manual_player_id
                else config.supported_agent_type
            ),
        )
        for index in range(1, player_count + 1)
    ]


def _authorize_manual_player(
    run: StoredGame,
    player_id: str,
    *,
    trusted_user_id: str | None = None,
) -> None:
    if player_id not in _manual_player_ids(run.config):
        raise AppError(MESSAGE_PLAYER_IS_NOT_MANUAL, code=ErrorCode.AUTHORIZATION_FAILED)
    if trusted_user_id is not None and trusted_user_id.strip():
        return
    raise AppError(
        MESSAGE_PLAYER_AUTHENTICATION_REQUIRED,
        code=ErrorCode.AUTHENTICATION_REQUIRED,
    )


def _manual_player_ids(config: Mapping[str, object]) -> set[str]:
    agent_types = config.get("player_agent_types")
    if not isinstance(agent_types, dict):
        return set()
    return {
        str(player_id) for player_id, agent_type in agent_types.items() if agent_type == "manual"
    }


def _player_profile_ids(config: Mapping[str, object]) -> dict[str, str]:
    profile_ids = config.get("player_profile_ids")
    if not isinstance(profile_ids, dict):
        return {}
    return {str(player_id): str(profile_id) for player_id, profile_id in profile_ids.items()}


def _manual_input_required(
    game: Game,
    manual_player_ids: set[str],
) -> bool:
    snapshot = game.snapshot()
    return any(
        player_id in snapshot.players and bool(game.view_for(player_id).available_actions)
        for player_id in manual_player_ids
    )


def _runtime_seed(seed: int | None, version: int) -> int:
    return runtime_seed(seed, version)
