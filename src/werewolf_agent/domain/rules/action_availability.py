"""Action availability rules shared by observations and action submission."""

from __future__ import annotations

from werewolf_agent.domain._messages import message_action_not_available
from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rules.player_rules import player_by_id
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    AvailableAction,
    GameState,
    PendingActions,
    Phase,
    PlayerStatus,
)


def available_actions(
    snapshot: GameState,
    pending_actions: PendingActions,
    player_id: str,
) -> list[AvailableAction]:
    """Return the concrete actions a player may submit right now."""
    player = player_by_id(snapshot, player_id)
    if player.status is not PlayerStatus.ALIVE:
        return []
    if snapshot.phase is Phase.DAY_DISCUSSION:
        round_ = pending_actions.discussion_round
        if round_ is None or player_id in pending_actions.discussion_actions:
            return []
        if player_id not in round_.actor_order:
            return []
        if round_.current_actor_id is not None and round_.current_actor_id != player_id:
            return []
        return [AvailableAction(ActionType.SPEECH), AvailableAction(ActionType.PASS)]
    if snapshot.phase is Phase.VOTING:
        if snapshot.config.voting.allow_revision or player_id not in pending_actions.votes:
            return [AvailableAction(ActionType.VOTE)]
        return []
    if snapshot.phase is not Phase.NIGHT:
        return []
    if (
        not snapshot.config.night.allow_action_revision
        and player_id in pending_actions.night_actions
    ):
        return []
    if player.role is None:
        return []
    role = snapshot.config.roles.require_role(player.role)
    actions: list[AvailableAction] = []
    for ability_id in role.abilities:
        ability = snapshot.config.abilities[ability_id]
        if ability.kind not in {"attack", "inspect", "protect", "eliminate"}:
            continue
        if ability.phase is not snapshot.phase or snapshot.day < ability.start_day:
            continue
        if snapshot.day == 1 and not ability.enabled_first_night:
            continue
        used = snapshot.ability_uses.get(player_id, {}).get(ability_id, 0)
        if ability.max_uses is not None and used >= ability.max_uses:
            continue
        actions.append(AvailableAction(ActionType.USE_ABILITY, ability_id))
    if actions and snapshot.config.night.allow_pass:
        actions.append(AvailableAction(ActionType.PASS))
    return actions


def legal_targets(
    snapshot: GameState,
    pending_actions: PendingActions,
    player_id: str,
) -> dict[str, list[str]]:
    """Return legal target ids keyed by action type or ability id."""
    options = available_actions(snapshot, pending_actions, player_id)
    alive_ids = [player.id for player in snapshot.players.values() if player.is_alive]
    targets: dict[str, list[str]] = {}
    for option in options:
        if option.type is ActionType.VOTE:
            candidates = list(pending_actions.revote_candidates) or alive_ids
            targets[option.key] = [
                target_id
                for target_id in candidates
                if snapshot.config.voting.allow_self_vote or target_id != player_id
            ]
            continue
        if option.ability_id is not None:
            targets[option.key] = _ability_targets(
                snapshot,
                player_id,
                option.ability_id,
                alive_ids,
            )
    return targets


def _ability_targets(
    snapshot: GameState,
    player_id: str,
    ability_id: str,
    alive_ids: list[str],
) -> list[str]:
    player = player_by_id(snapshot, player_id)
    if player.role is None:
        return []
    role = snapshot.config.roles.require_role(player.role)
    if ability_id not in role.abilities:
        return []
    ability = snapshot.config.abilities[ability_id]
    targets = list(alive_ids)
    if ability.target_policy in {"other_alive", "other_alive_non_faction"}:
        targets = [target_id for target_id in targets if target_id != player_id]
    if ability.target_policy == "other_alive_non_faction":
        targets = [
            target_id
            for target_id in targets
            if _player_faction(snapshot, target_id) != role.identity_faction
        ]
    if not ability.allow_repeat_target:
        previous_target = _previous_ability_target(snapshot, player_id, ability_id)
        if previous_target is not None:
            targets = [target_id for target_id in targets if target_id != previous_target]
    return targets


def _previous_ability_target(
    snapshot: GameState,
    player_id: str,
    ability_id: str,
) -> str | None:
    for night in reversed(snapshot.history.nights):
        target_id = night.ability_targets.get(player_id, {}).get(ability_id)
        if target_id is not None:
            return target_id
    return None


def _player_faction(snapshot: GameState, player_id: str) -> str | None:
    role = snapshot.players[player_id].role
    return None if role is None else snapshot.config.roles.faction_for_role(role)


def require_action_available(
    snapshot: GameState,
    pending_actions: PendingActions,
    action: Action,
) -> None:
    """Raise when an action is not currently accepted by the game rules."""
    options = available_actions(snapshot, pending_actions, action.player_id)
    requested = AvailableAction(action.type, action.ability_id)
    if requested not in options:
        raise GameError(
            message_action_not_available(requested.key, snapshot.phase.value),
            context={
                "player_id": action.player_id,
                "action_type": action.type.value,
                "ability_id": action.ability_id,
                "phase": snapshot.phase.value,
                "day": snapshot.day,
            },
        )
    if action.target_id is not None and action.target_id not in legal_targets(
        snapshot,
        pending_actions,
        action.player_id,
    ).get(requested.key, []):
        raise GameError(
            message_action_not_available(requested.key, snapshot.phase.value),
            context={"player_id": action.player_id, "target_id": action.target_id},
        )
