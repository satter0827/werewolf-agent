"""Night action recording and resolution rules."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping

from werewolf_agent.contracts import GameError
from werewolf_agent.domain.models import (
    Action,
    ActionType,
    GameSnapshot,
    InspectionResult,
    NightResult,
    Phase,
    Role,
)
from werewolf_agent.domain.rules.player_rules import (
    faction_for_role,
    mark_dead,
    player_by_id,
    require_alive,
    require_phase,
    require_role,
)


def record_night_action(
    snapshot: GameSnapshot,
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
    snapshot: GameSnapshot,
    pending_actions: Mapping[str, Action],
    rng: random.Random,
) -> tuple[GameSnapshot, NightResult]:
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
        inspections=inspection_results,
    )
    history = updated_snapshot.history.model_copy(
        update={"nights": [*updated_snapshot.history.nights, result]}
    )
    return updated_snapshot.model_copy(update={"history": history}), result


def _validate_night_action(snapshot: GameSnapshot, action: Action) -> None:
    target_id = _night_target(action)
    if action.type is ActionType.WEREWOLF_ATTACK:
        require_role(snapshot, action.player_id, Role.WEREWOLF)
        target = require_alive(snapshot, target_id)
        if target.role is Role.WEREWOLF:
            raise GameError(
                "Werewolves cannot attack another werewolf.",
                context={"player_id": action.player_id, "target_id": target_id},
            )
        return
    if action.type is ActionType.SEER_INSPECT:
        require_role(snapshot, action.player_id, Role.SEER)
        require_alive(snapshot, target_id)
        if action.player_id == target_id:
            raise GameError(
                "Seer cannot inspect themself.",
                context={"player_id": action.player_id, "target_id": target_id},
            )
        return
    if action.type is ActionType.KNIGHT_GUARD:
        require_role(snapshot, action.player_id, Role.KNIGHT)
        require_alive(snapshot, target_id)
        return
    raise GameError("Unsupported night action.")


def _night_target(action: Action) -> str:
    if not action.is_night_action or action.target_id is None:
        raise GameError("Expected a night action.")
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


def _inspect(snapshot: GameSnapshot, action: Action) -> InspectionResult:
    seer = require_alive(snapshot, action.player_id)
    target = player_by_id(snapshot, _night_target(action))
    if target.role is None:
        raise GameError(
            "Cannot inspect a player before roles are assigned.",
            context={"target_id": target.id},
        )
    return InspectionResult(
        day=snapshot.day,
        seer_id=seer.id,
        target_id=target.id,
        target_role=target.role,
        target_faction=faction_for_role(target.role),
    )
