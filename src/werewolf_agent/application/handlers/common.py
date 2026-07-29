"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from werewolf_agent.application.constants import (
    DEFAULT_NARRATION_MODE,
    MIN_PAGE_LIMIT,
    NARRATION_MODE_CHOICES,
    NarrationMode,
)
from werewolf_agent.application.definitions import (
    NarrationEventDefinition,
    NarrationProfileDefinition,
)
from werewolf_agent.application.domain_codec import action_from_data, game_state_from_data
from werewolf_agent.application.errors import (
    AppError,
    ErrorCode,
    GameError,
    InvalidGameIdError,
)
from werewolf_agent.application.messages import (
    MESSAGE_GAME_ID_MUST_BE_VALID_UUID,
    MESSAGE_PLAYER_AUTHENTICATION_REQUIRED,
    MESSAGE_PLAYER_IS_NOT_MANUAL,
    message_field_must_be_between,
    message_unsupported_action_type,
)
from werewolf_agent.application.models import (
    GameRevealAction,
    PlayerActionCommand,
    StoredGame,
)
from werewolf_agent.application.randomness import runtime_seed
from werewolf_agent.application.rules import rule_definition_from_state
from werewolf_agent.domain import (
    Action,
    Game,
    GameState,
    build_game_rules,
)


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


def _narration_profile(
    config: Mapping[str, object],
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
    return None


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
        ability_id=action.ability_id,
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
                "ability_id": command.ability_id,
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
    state = game_state_from_data({**run.private_state, "pending_actions": run.pending_actions})
    rules = build_game_rules(rule_definition_from_state(state))
    return Game.restore(state, rules=rules)


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
