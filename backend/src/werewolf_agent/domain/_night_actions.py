"""Night action recording and resolution."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping

from werewolf_agent.commons import GameError
from werewolf_agent.domain._rules import (
    faction_for_role,
    mark_dead,
    player_by_id,
    require_alive,
    require_phase,
    require_role,
)
from werewolf_agent.domain.models import (
    GameSnapshot,
    KnightGuardAction,
    NightAction,
    NightResult,
    Phase,
    Role,
    SeerInspectAction,
    SeerInspectionResult,
    WerewolfAttackAction,
)


def record_night_action(
    snapshot: GameSnapshot,
    pending_actions: Mapping[str, NightAction],
    action: NightAction,
) -> dict[str, NightAction]:
    """Validate and return pending night actions with one action recorded."""
    require_phase(snapshot, Phase.NIGHT)
    _validate_night_action(snapshot, action)

    updated_actions = dict(pending_actions)
    updated_actions[action.player_id] = action
    return updated_actions


def resolve_night(
    snapshot: GameSnapshot,
    pending_actions: Mapping[str, NightAction],
    rng: random.Random,
) -> tuple[GameSnapshot, NightResult]:
    """Resolve all currently pending night actions."""
    require_phase(snapshot, Phase.NIGHT)

    attacks = [
        action for action in pending_actions.values() if isinstance(action, WerewolfAttackAction)
    ]
    guards = [
        action for action in pending_actions.values() if isinstance(action, KnightGuardAction)
    ]
    inspections = [
        action for action in pending_actions.values() if isinstance(action, SeerInspectAction)
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
    updated_history = [*updated_snapshot.night_history, result]
    return updated_snapshot.model_copy(update={"night_history": updated_history}), result


def _validate_night_action(snapshot: GameSnapshot, action: NightAction) -> None:
    if isinstance(action, WerewolfAttackAction):
        require_role(snapshot, action.player_id, Role.WEREWOLF)
        target = require_alive(snapshot, action.target_id)
        if target.role is Role.WEREWOLF:
            raise GameError(
                "Werewolves cannot attack another werewolf.",
                context={"player_id": action.player_id, "target_id": action.target_id},
            )
        return
    if isinstance(action, SeerInspectAction):
        require_role(snapshot, action.player_id, Role.SEER)
        require_alive(snapshot, action.target_id)
        if action.player_id == action.target_id:
            raise GameError(
                "Seer cannot inspect themself.",
                context={"player_id": action.player_id, "target_id": action.target_id},
            )
        return
    if isinstance(action, KnightGuardAction):
        require_role(snapshot, action.player_id, Role.KNIGHT)
        require_alive(snapshot, action.target_id)
        return
    raise GameError("Unsupported night action.")


def _resolve_attack_target(
    attacks: list[WerewolfAttackAction],
    rng: random.Random,
) -> str | None:
    if not attacks:
        return None
    counts = Counter(action.target_id for action in attacks)
    max_votes = max(counts.values())
    tied_targets = sorted(target_id for target_id, count in counts.items() if count == max_votes)
    return tied_targets[0] if len(tied_targets) == 1 else rng.choice(tied_targets)


def _resolve_guard_target(guards: list[KnightGuardAction]) -> str | None:
    if not guards:
        return None
    return sorted(guards, key=lambda action: action.player_id)[0].target_id


def _inspect(snapshot: GameSnapshot, action: SeerInspectAction) -> SeerInspectionResult:
    seer = require_alive(snapshot, action.player_id)
    target = player_by_id(snapshot, action.target_id)
    return SeerInspectionResult(
        day=snapshot.day,
        seer_id=seer.player_id,
        target_id=target.player_id,
        target_role=target.role,
        target_faction=faction_for_role(target.role),
    )
