"""Action availability rules shared by observations and action submission."""

from __future__ import annotations

from werewolf_agent.commons.shared.messages import message_action_not_available
from werewolf_agent.contracts import GameError
from werewolf_agent.domain.game.models import (
    Action,
    ActionType,
    GameSnapshot,
    PendingActions,
    Phase,
    PlayerStatus,
    Role,
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
        if _speech_count_for_today(snapshot, player_id) < snapshot.config.day_speech_turns:
            return [ActionType.SPEECH]
        return []
    if snapshot.phase is Phase.VOTING:
        if snapshot.config.allow_action_revisions or player_id not in pending_actions.votes:
            return [ActionType.VOTE]
        return []
    if snapshot.phase is Phase.NIGHT:
        has_submitted = player_id in pending_actions.night_actions
        if not snapshot.config.allow_action_revisions and has_submitted:
            return []
        if player.role is Role.WEREWOLF:
            return [ActionType.WEREWOLF_ATTACK]
        if player.role is Role.SEER:
            return [ActionType.SEER_INSPECT]
        if player.role is Role.KNIGHT:
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
