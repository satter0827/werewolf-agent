"""Translate validated application definitions into executable domain rules."""

from __future__ import annotations

from collections.abc import Mapping

from werewolf_agent.domain import RuleSetDefinition
from werewolf_agent.domain.state import (
    AbilityDefinition,
    GameState,
    LocalRules,
    Phase,
    RoleCatalog,
    RoleDefinition,
)


def rule_definition_from_values(
    *,
    player_count: int,
    role_counts: Mapping[str, int],
    rules: Mapping[str, object],
    roles: Mapping[str, Mapping[str, object]],
    abilities: Mapping[str, Mapping[str, object]],
) -> RuleSetDefinition:
    """Build typed domain rule data from validated application resources."""
    return RuleSetDefinition(
        player_count=player_count,
        role_counts=role_counts,
        rules=LocalRules(**dict(rules)),  # type: ignore[arg-type]
        roles=RoleCatalog(
            roles={
                role_id: RoleDefinition(
                    identity_faction=str(value.get("identity_faction")),
                    victory_team=str(value.get("victory_team")),
                    abilities=tuple(str(item) for item in _sequence_value(value.get("abilities"))),
                )
                for role_id, value in roles.items()
            }
        ),
        abilities={
            ability_id: AbilityDefinition(
                kind=str(value.get("kind")),
                phase=Phase(str(value.get("phase"))),
                target_policy=str(value.get("target_policy")),
                start_day=_integer_value(value.get("start_day")),
                max_uses=(
                    None
                    if value.get("max_uses") == "unlimited"
                    else _integer_value(value.get("max_uses"))
                ),
                result_visibility=str(value.get("result_visibility")),
                resolution_priority=_integer_value(value.get("resolution_priority")),
                allow_repeat_target=bool(value.get("allow_repeat_target")),
                enabled_first_night=bool(value.get("enabled_first_night")),
                result_detail=(
                    None if value.get("result_detail") is None else str(value["result_detail"])
                ),
                knowledge_mode=(
                    None if value.get("knowledge_mode") is None else str(value["knowledge_mode"])
                ),
                tie_resolution=(
                    None if value.get("tie_resolution") is None else str(value["tie_resolution"])
                ),
                source_kinds=tuple(
                    str(item) for item in _sequence_value(value.get("source_kinds"))
                ),
            )
            for ability_id, value in abilities.items()
        },
    )


def rule_definition_from_state(
    state: GameState,
) -> RuleSetDefinition:
    """Restore typed rule data from one persisted aggregate snapshot."""
    config = state.config
    return RuleSetDefinition(
        player_count=config.player_count,
        role_counts=config.role_counts,
        rules=config.rules,
        roles=config.roles,
        abilities=config.abilities,
    )


def _sequence_value(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("rule sequence value must be an array")
    return tuple(value)


def _integer_value(value: object) -> int:
    if value is None:
        raise ValueError("rule integer value is required")
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        raise ValueError("rule integer value must be numeric")
    return int(value)


__all__ = ["rule_definition_from_state", "rule_definition_from_values"]
