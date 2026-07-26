"""Action availability rules shared by observations and action submission."""

from __future__ import annotations

from werewolf_agent.domain._messages import message_action_not_available
from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rules.player_rules import player_by_id
from werewolf_agent.domain.state import (
    ABILITY_NIGHT_ATTACK,
    Action,
    ActionType,
    GameState,
    PendingActions,
    Phase,
    PlayerStatus,
)


def available_actions(
    snapshot: GameState,
    pending_actions: PendingActions,
    player_id: str,
) -> list[ActionType]:
    """Return the actions a player may submit right now."""
    player = player_by_id(snapshot, player_id)
    if player.status is not PlayerStatus.ALIVE:
        return []
    if snapshot.phase is Phase.DAY_DISCUSSION:
        if (
            _speech_count_for_today(snapshot, player_id)
            < snapshot.config.rules.day_speech_limit_per_player
        ):
            return [ActionType.SPEECH]
        return []
    if snapshot.phase is Phase.VOTING:
        if snapshot.config.rules.allow_vote_revision or player_id not in pending_actions.votes:
            return [ActionType.VOTE]
        return []
    if snapshot.phase is Phase.NIGHT:
        has_submitted = player_id in pending_actions.night_actions
        if not snapshot.config.rules.allow_night_action_revision and has_submitted:
            return []
        if player.role is None:
            return []
        role = snapshot.config.roles.require_role(player.role)
        actions: list[ActionType] = []
        for ability_id in role.abilities:
            ability = snapshot.config.abilities[ability_id]
            if ability.phase is not snapshot.phase or snapshot.day < ability.start_day:
                continue
            used = snapshot.ability_uses.get(player_id, {}).get(ability_id, 0)
            if ability.max_uses is not None and used >= ability.max_uses:
                continue
            if ability.action is ActionType.PASS:
                continue
            if (
                ability_id == ABILITY_NIGHT_ATTACK
                and snapshot.day == 1
                and not snapshot.config.rules.enable_first_night_attack
            ):
                continue
            if ability.action not in actions:
                actions.append(ability.action)
        return actions
    return []


def legal_targets(
    snapshot: GameState,
    pending_actions: PendingActions,
    player_id: str,
) -> dict[ActionType, list[str]]:
    """Return legal target ids for each currently available action."""
    actions = available_actions(snapshot, pending_actions, player_id)
    alive_ids = [player.id for player in snapshot.players.values() if player.is_alive]
    targets: dict[ActionType, list[str]] = {}
    for action_type in actions:
        if action_type is ActionType.VOTE:
            candidate_ids = (
                list(pending_actions.revote_candidates)
                if pending_actions.revote_candidates
                else alive_ids
            )
            targets[action_type] = [
                target_id
                for target_id in candidate_ids
                if snapshot.config.rules.allow_self_vote or target_id != player_id
            ]
            continue
        if action_type not in {
            ActionType.WEREWOLF_ATTACK,
            ActionType.SEER_INSPECT,
            ActionType.KNIGHT_GUARD,
            ActionType.APOTHECARY_HEAL,
            ActionType.APOTHECARY_POISON,
        }:
            continue
        targets[action_type] = _night_targets(snapshot, player_id, action_type, alive_ids)
    return targets


def _night_targets(
    snapshot: GameState,
    player_id: str,
    action_type: ActionType,
    alive_ids: list[str],
) -> list[str]:
    player = player_by_id(snapshot, player_id)
    if player.role is None:
        return []
    role = snapshot.config.roles.require_role(player.role)
    ability = next(
        (
            snapshot.config.abilities[ability_id]
            for ability_id in role.abilities
            if snapshot.config.abilities[ability_id].action is action_type
        ),
        None,
    )
    if ability is None:
        return []
    targets = list(alive_ids)
    excludes_self = ability.target_policy in {"other_alive", "other_alive_non_pack"}
    if action_type is ActionType.SEER_INSPECT and snapshot.config.rules.allow_seer_self_inspect:
        excludes_self = False
    if action_type is ActionType.KNIGHT_GUARD and snapshot.config.rules.allow_knight_self_guard:
        excludes_self = False
    if excludes_self:
        targets = [target_id for target_id in targets if target_id != player_id]
    if (
        ability.target_policy == "other_alive_non_pack"
        and action_type is ActionType.WEREWOLF_ATTACK
        and not snapshot.config.rules.allow_werewolf_friendly_fire
    ):
        actor_faction = role.identity_faction
        targets = [
            target_id
            for target_id in targets
            if _player_faction(snapshot, target_id) != actor_faction
        ]
    if (
        action_type is ActionType.KNIGHT_GUARD
        and not snapshot.config.rules.allow_knight_repeat_guard
        and snapshot.history.nights
    ):
        previous_target = snapshot.history.nights[-1].protected_player_id
        targets = [target_id for target_id in targets if target_id != previous_target]
    return targets


def _player_faction(snapshot: GameState, player_id: str) -> str | None:
    role = snapshot.players[player_id].role
    return None if role is None else snapshot.config.roles.faction_for_role(role)


def require_action_available(
    snapshot: GameState,
    pending_actions: PendingActions,
    action: Action,
) -> None:
    """Raise when an action is not currently accepted by the game rules."""
    if action.type not in available_actions(snapshot, pending_actions, action.player_id):
        raise GameError(
            message_action_not_available(action.type.value, snapshot.phase.value),
            context={
                "player_id": action.player_id,
                "action_type": action.type.value,
                "phase": snapshot.phase.value,
                "day": snapshot.day,
            },
        )


def _speech_count_for_today(snapshot: GameState, player_id: str) -> int:
    return sum(
        1
        for speech in snapshot.history.speeches
        if speech.day == snapshot.day and speech.player_id == player_id
    )
