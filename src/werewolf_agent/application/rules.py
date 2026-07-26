"""Translate validated application definitions into executable domain rules."""

from __future__ import annotations

from collections.abc import Mapping

from werewolf_agent.domain import RuleSetDefinition
from werewolf_agent.domain.state import (
    AbilityDefinition,
    ActionType,
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
    composition: Mapping[str, object],
) -> RuleSetDefinition:
    """Build typed domain rule data from validated application resources."""
    return RuleSetDefinition(
        player_count=player_count,
        role_counts=role_counts,
        rules=LocalRules(**dict(rules)),  # type: ignore[arg-type]
        roles=RoleCatalog(
            roles={
                role_id: RoleDefinition(
                    faction=str(value.get("faction")),
                    abilities=tuple(str(item) for item in _sequence_value(value.get("abilities"))),
                )
                for role_id, value in roles.items()
            }
        ),
        abilities={
            ability_id: AbilityDefinition(
                phase=Phase(str(value.get("phase"))),
                action=ActionType(str(value.get("action"))),
                validation_policy=str(value.get("validation_policy")),
                resolution_policy=str(value.get("resolution_policy")),
                target_policy=str(value.get("target_policy")),
                start_day=_integer_value(value.get("start_day"), default=1),
            )
            for ability_id, value in abilities.items()
        },
        phases=_phase_ids(composition),
        action_policy=_policy_id(composition, "action_policy", "standard"),
        resolution_policy=_policy_id(composition, "resolution_policy", "standard"),
        phase_policy=_policy_id(composition, "phase_policy", "required_actions"),
        victory_policy=_policy_id(composition, "victory_policy", "faction_balance"),
        visibility_policy=_policy_id(composition, "visibility_policy", "standard"),
    )


def rule_definition_from_state(
    state: GameState,
    composition: Mapping[str, object],
) -> RuleSetDefinition:
    """Restore typed rule data from one persisted aggregate snapshot."""
    config = state.config
    return RuleSetDefinition(
        player_count=config.player_count,
        role_counts=config.role_counts,
        rules=config.rules,
        roles=config.roles,
        abilities=config.abilities,
        phases=tuple(phase.value for phase in config.phase_order),
        action_policy=_policy_id(composition, "action_policy", "standard"),
        resolution_policy=_policy_id(composition, "resolution_policy", "standard"),
        phase_policy=_policy_id(composition, "phase_policy", "required_actions"),
        victory_policy=_policy_id(composition, "victory_policy", "faction_balance"),
        visibility_policy=_policy_id(composition, "visibility_policy", "standard"),
    )


def _policy_id(composition: Mapping[str, object], key: str, default: str) -> str:
    return str(composition.get(key, default))


def _phase_ids(composition: Mapping[str, object]) -> tuple[str, ...]:
    value = composition.get("phases")
    if not isinstance(value, (list, tuple)):
        return ("night", "day_discussion", "voting")
    return tuple(str(phase) for phase in value)


def _sequence_value(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("rule sequence value must be an array")
    return tuple(value)


def _integer_value(value: object, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        raise ValueError("rule integer value must be numeric")
    return int(value)


__all__ = ["rule_definition_from_state", "rule_definition_from_values"]
