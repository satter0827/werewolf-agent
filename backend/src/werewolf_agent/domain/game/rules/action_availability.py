"""Action availability rules shared by observations and action submission."""

from __future__ import annotations

from werewolf_agent.commons.shared.exceptions import GameError
from werewolf_agent.commons.shared.messages import message_action_not_available
from werewolf_agent.domain.game.models import (
    ABILITY_GUARD,
    ABILITY_INSPECT,
    ABILITY_NIGHT_ATTACK,
    Action,
    ActionType,
    GameSnapshot,
    PendingActions,
    Phase,
    PlayerStatus,
)
from werewolf_agent.domain.game.rules.player_rules import player_by_id


def available_actions(
    snapshot: GameSnapshot,
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
        if snapshot.day == 1 and not snapshot.config.rules.enable_first_night_attack:
            attack_enabled = False
        else:
            attack_enabled = True
        roles = snapshot.config.roles
        if attack_enabled and roles.role_has_ability(player.role, ABILITY_NIGHT_ATTACK):
            return [ActionType.WEREWOLF_ATTACK]
        if roles.role_has_ability(player.role, ABILITY_INSPECT):
            return [ActionType.SEER_INSPECT]
        if roles.role_has_ability(player.role, ABILITY_GUARD):
            return [ActionType.KNIGHT_GUARD]
    return []


def require_action_available(
    snapshot: GameSnapshot,
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


def _speech_count_for_today(snapshot: GameSnapshot, player_id: str) -> int:
    return sum(
        1
        for speech in snapshot.history.speeches
        if speech.day == snapshot.day and speech.player_id == player_id
    )
