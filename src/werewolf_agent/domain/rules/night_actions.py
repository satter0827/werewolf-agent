"""Night action recording and resolution rules."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace

from werewolf_agent.domain._messages import (
    MESSAGE_CANNOT_INSPECT_UNASSIGNED_ROLE,
    MESSAGE_EXPECTED_NIGHT_ACTION,
    MESSAGE_KNIGHT_CANNOT_GUARD_SELF,
    MESSAGE_KNIGHT_CANNOT_REPEAT_GUARD_TARGET,
    MESSAGE_SEER_CANNOT_INSPECT_SELF,
    MESSAGE_UNSUPPORTED_NIGHT_ACTION,
    MESSAGE_WEREWOLVES_CANNOT_ATTACK_WEREWOLF,
)
from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rules.player_rules import (
    faction_for_role,
    mark_dead,
    player_by_id,
    require_alive,
    require_phase,
)
from werewolf_agent.domain.state import (
    FACTION_WEREWOLF,
    AbilityDefinition,
    Action,
    ActionType,
    GameState,
    InspectionResult,
    NightResult,
    Phase,
)


def record_night_action(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
    action: Action,
) -> dict[str, Action]:
    """Validate and return pending night actions with one action recorded."""
    require_phase(snapshot, Phase.NIGHT)
    _validate_night_action(snapshot, action)

    updated_actions = dict(pending_actions)
    updated_actions[action.player_id] = action
    return updated_actions


def resolve_night(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
    rng: random.Random,
) -> tuple[GameState, NightResult]:
    """Resolve all currently pending night actions."""
    require_phase(snapshot, Phase.NIGHT)

    attacks = [
        action for action in pending_actions.values() if action.type is ActionType.WEREWOLF_ATTACK
    ]
    guards = [
        action for action in pending_actions.values() if action.type is ActionType.KNIGHT_GUARD
    ]
    inspections = [
        action for action in pending_actions.values() if action.type is ActionType.SEER_INSPECT
    ]

    attacked_player_id = _resolve_attack_target(attacks, rng)
    protected_player_id = _resolve_guard_target(guards)
    killed_player_id = (
        attacked_player_id
        if attacked_player_id is not None and attacked_player_id != protected_player_id
        else None
    )

    updated_snapshot = snapshot
    if killed_player_id is not None:
        updated_snapshot = mark_dead(snapshot, killed_player_id, killed_night=snapshot.day)

    inspection_results = [_inspect(snapshot, action) for action in inspections]
    result = NightResult(
        day=snapshot.day,
        attacked_player_id=attacked_player_id,
        protected_player_id=protected_player_id,
        killed_player_id=killed_player_id,
        inspections=tuple(inspection_results),
    )
    history = replace(updated_snapshot.history, nights=(*updated_snapshot.history.nights, result))
    return replace(updated_snapshot, history=history), result


def _validate_night_action(snapshot: GameState, action: Action) -> None:
    target_id = _night_target(action)
    ability = _ability_for_action(snapshot, action)
    target = require_alive(snapshot, target_id)
    if action.type is ActionType.WEREWOLF_ATTACK:
        if (
            ability.target_policy == "other_alive_non_pack"
            and not snapshot.config.rules.allow_werewolf_friendly_fire
            and target.role is not None
            and faction_for_role(snapshot, target.role) == FACTION_WEREWOLF
        ):
            raise GameError(
                MESSAGE_WEREWOLVES_CANNOT_ATTACK_WEREWOLF,
                context={"player_id": action.player_id, "target_id": target_id},
            )
        return
    if action.type is ActionType.SEER_INSPECT:
        if action.player_id == target_id and (
            ability.target_policy in {"other_alive", "other_alive_non_pack"}
            or not snapshot.config.rules.allow_seer_self_inspect
        ):
            raise GameError(
                MESSAGE_SEER_CANNOT_INSPECT_SELF,
                context={"player_id": action.player_id, "target_id": target_id},
            )
        return
    if action.type is ActionType.KNIGHT_GUARD:
        if action.player_id == target_id and (
            ability.target_policy in {"other_alive", "other_alive_non_pack"}
            or not snapshot.config.rules.allow_knight_self_guard
        ):
            raise GameError(
                MESSAGE_KNIGHT_CANNOT_GUARD_SELF,
                context={"player_id": action.player_id, "target_id": target_id},
            )
        last_night = snapshot.history.nights[-1] if snapshot.history.nights else None
        if (
            not snapshot.config.rules.allow_knight_repeat_guard
            and last_night is not None
            and last_night.protected_player_id == target_id
        ):
            raise GameError(
                MESSAGE_KNIGHT_CANNOT_REPEAT_GUARD_TARGET,
                context={"player_id": action.player_id, "target_id": target_id},
            )
        return
    raise GameError(MESSAGE_UNSUPPORTED_NIGHT_ACTION)


def _ability_for_action(snapshot: GameState, action: Action) -> AbilityDefinition:
    actor = require_alive(snapshot, action.player_id)
    if actor.role is None:
        raise GameError(MESSAGE_UNSUPPORTED_NIGHT_ACTION)
    role = snapshot.config.roles.require_role(actor.role)
    for ability_id in role.abilities:
        ability = snapshot.config.abilities[ability_id]
        if ability.action is action.type:
            return ability
    raise GameError(
        MESSAGE_UNSUPPORTED_NIGHT_ACTION,
        context={"player_id": action.player_id, "action_type": action.type.value},
    )


def _night_target(action: Action) -> str:
    if not action.is_night_action or action.target_id is None:
        raise GameError(MESSAGE_EXPECTED_NIGHT_ACTION)
    return action.target_id


def _resolve_attack_target(
    attacks: list[Action],
    rng: random.Random,
) -> str | None:
    if not attacks:
        return None
    counts = Counter(_night_target(action) for action in attacks)
    max_votes = max(counts.values())
    tied_targets = sorted(target_id for target_id, count in counts.items() if count == max_votes)
    return tied_targets[0] if len(tied_targets) == 1 else rng.choice(tied_targets)


def _resolve_guard_target(guards: list[Action]) -> str | None:
    if not guards:
        return None
    return _night_target(sorted(guards, key=lambda action: action.player_id)[0])


def _inspect(snapshot: GameState, action: Action) -> InspectionResult:
    seer = require_alive(snapshot, action.player_id)
    target = player_by_id(snapshot, _night_target(action))
    if target.role is None:
        raise GameError(
            MESSAGE_CANNOT_INSPECT_UNASSIGNED_ROLE,
            context={"target_id": target.id},
        )
    return InspectionResult(
        day=snapshot.day,
        seer_id=seer.id,
        target_id=target.id,
        target_role=target.role,
        target_faction=faction_for_role(snapshot, target.role),
    )
