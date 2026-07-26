"""Night action recording and resolution rules."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Mapping
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
    resolve_death_reactions,
)
from werewolf_agent.domain.state import (
    ABILITY_ATTACK_IMMUNITY,
    ABILITY_INSPECTION_VULNERABILITY,
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
    heals = [
        action for action in pending_actions.values() if action.type is ActionType.APOTHECARY_HEAL
    ]
    poisons = [
        action for action in pending_actions.values() if action.type is ActionType.APOTHECARY_POISON
    ]
    inspections = [
        action for action in pending_actions.values() if action.type is ActionType.SEER_INSPECT
    ]

    attacked_player_id = _resolve_attack_target(
        attacks,
        rng,
        tie_resolution=snapshot.config.rules.wolf_attack_tie_resolution,
    )
    protected_player_ids = {
        target_id
        for target_id in (
            _resolve_guard_target(guards),
            *(_night_target(action) for action in heals),
        )
        if target_id is not None
    }
    killed_player_ids: set[str] = {
        _night_target(action) for action in poisons
    } - protected_player_ids
    if (
        attacked_player_id is not None
        and attacked_player_id not in protected_player_ids
        and not _role_has_ability(snapshot, attacked_player_id, ABILITY_ATTACK_IMMUNITY)
    ):
        killed_player_ids.add(attacked_player_id)

    updated_snapshot = snapshot
    for killed_player_id in sorted(killed_player_ids):
        updated_snapshot = mark_dead(
            updated_snapshot,
            killed_player_id,
            killed_night=snapshot.day,
        )

    inspection_results = [_inspect(snapshot, action) for action in inspections]
    inspected_vulnerable_ids = {
        result.target_id
        for result in inspection_results
        if _role_has_ability(snapshot, result.target_id, ABILITY_INSPECTION_VULNERABILITY)
    }
    for player_id in sorted(inspected_vulnerable_ids - killed_player_ids):
        updated_snapshot = mark_dead(
            updated_snapshot,
            player_id,
            killed_night=snapshot.day,
        )
    killed_player_ids.update(inspected_vulnerable_ids)
    updated_snapshot, reaction_deaths = resolve_death_reactions(
        updated_snapshot,
        sorted(killed_player_ids),
        rng,
        during_night=True,
    )
    killed_player_ids.update(reaction_deaths)
    updated_snapshot = _consume_limited_abilities(updated_snapshot, pending_actions.values())
    killed_ids = tuple(sorted(killed_player_ids))
    result = NightResult(
        day=snapshot.day,
        attacked_player_id=attacked_player_id,
        protected_player_id=next(iter(sorted(protected_player_ids)), None),
        killed_player_id=killed_ids[0] if killed_ids else None,
        killed_player_ids=killed_ids,
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
    if action.type in {ActionType.APOTHECARY_HEAL, ActionType.APOTHECARY_POISON}:
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
    *,
    tie_resolution: str,
) -> str | None:
    if not attacks:
        return None
    counts = Counter(_night_target(action) for action in attacks)
    max_votes = max(counts.values())
    tied_targets = sorted(target_id for target_id, count in counts.items() if count == max_votes)
    if len(tied_targets) == 1:
        return tied_targets[0]
    if tie_resolution == "no_attack":
        return None
    return rng.choice(tied_targets)


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


def _role_has_ability(snapshot: GameState, player_id: str, ability_id: str) -> bool:
    role = snapshot.players[player_id].role
    return snapshot.config.roles.role_has_ability(role, ability_id)


def _consume_limited_abilities(
    snapshot: GameState,
    actions: Iterable[Action],
) -> GameState:
    uses = {player_id: dict(values) for player_id, values in snapshot.ability_uses.items()}
    for action in actions:
        ability_id = _ability_id_for_action(snapshot, action)
        ability = snapshot.config.abilities[ability_id]
        if ability.max_uses is None:
            continue
        player_uses = uses.setdefault(action.player_id, {})
        player_uses[ability_id] = player_uses.get(ability_id, 0) + 1
    return replace(snapshot, ability_uses=uses)


def _ability_id_for_action(snapshot: GameState, action: Action) -> str:
    player = snapshot.players[action.player_id]
    if player.role is None:
        raise GameError(MESSAGE_UNSUPPORTED_NIGHT_ACTION)
    role = snapshot.config.roles.require_role(player.role)
    return next(
        ability_id
        for ability_id in role.abilities
        if snapshot.config.abilities[ability_id].action is action.type
    )
