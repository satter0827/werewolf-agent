"""Player state, faction, and win-condition rules."""

from __future__ import annotations

from werewolf_agent.commons.shared.messages import (
    message_expected_phase,
    message_player_cannot_perform_role_action,
    message_player_not_alive,
    message_unknown_player_id,
)
from werewolf_agent.contracts import GameError, GamePhaseError
from werewolf_agent.domain.game.models import (
    FACTION_VILLAGE,
    FACTION_WEREWOLF,
    GameSnapshot,
    Phase,
    Player,
    PlayerStatus,
    WinResult,
)


def faction_for_role(snapshot: GameSnapshot, role: str) -> str:
    """Return the faction for one role."""
    return snapshot.config.roles.faction_for_role(role)


def require_phase(snapshot: GameSnapshot, expected: Phase) -> None:
    """Raise if the game is not in the expected phase."""
    if snapshot.phase is not expected:
        raise GamePhaseError(
            message_expected_phase(expected.value, snapshot.phase.value),
            context={"expected_phase": expected.value, "current_phase": snapshot.phase.value},
        )


def player_by_id(snapshot: GameSnapshot, player_id: str) -> Player:
    """Return one player or raise a safe game error."""
    try:
        return snapshot.players[player_id]
    except KeyError as exc:
        raise GameError(
            message_unknown_player_id(player_id),
            context={"player_id": player_id},
        ) from exc


def require_alive(snapshot: GameSnapshot, player_id: str) -> Player:
    """Return one alive player or raise a safe game error."""
    player = player_by_id(snapshot, player_id)
    if player.status is not PlayerStatus.ALIVE:
        raise GameError(
            message_player_not_alive(player_id),
            context={"player_id": player_id, "status": player.status.value},
        )
    return player


def require_role(snapshot: GameSnapshot, player_id: str, expected: str) -> Player:
    """Return an alive player with the expected role."""
    player = require_alive(snapshot, player_id)
    if player.role != expected:
        actual_role = player.role if player.role is not None else None
        raise GameError(
            message_player_cannot_perform_role_action(player_id, expected),
            context={
                "player_id": player_id,
                "expected_role": expected,
                "actual_role": actual_role,
            },
        )
    return player


def alive_players(snapshot: GameSnapshot) -> list[Player]:
    """Return alive players in stable game order."""
    return [player for player in snapshot.players.values() if player.status is PlayerStatus.ALIVE]


def mark_dead(
    snapshot: GameSnapshot,
    player_id: str,
    *,
    eliminated_day: int | None = None,
    killed_night: int | None = None,
) -> GameSnapshot:
    """Return a copy of the snapshot with one player marked dead."""
    player = require_alive(snapshot, player_id)
    updated_player = player.model_copy(
        update={
            "status": PlayerStatus.DEAD,
            "eliminated_day": eliminated_day,
            "killed_night": killed_night,
        }
    )
    updated_players = dict(snapshot.players)
    updated_players[player_id] = updated_player
    return snapshot.model_copy(update={"players": updated_players})


def check_win(snapshot: GameSnapshot) -> WinResult | None:
    """Return a win result when either faction has met its win condition."""
    alive = alive_players(snapshot)
    alive_wolves = [
        player
        for player in alive
        if player.role is not None and faction_for_role(snapshot, player.role) == FACTION_WEREWOLF
    ]
    alive_village = [
        player
        for player in alive
        if player.role is not None and faction_for_role(snapshot, player.role) == FACTION_VILLAGE
    ]

    if not alive_wolves:
        return _win_result(snapshot, FACTION_VILLAGE, "all_werewolves_eliminated")
    if len(alive_wolves) >= len(alive_village):
        return _win_result(snapshot, FACTION_WEREWOLF, "werewolves_reached_parity")
    return None


def _win_result(snapshot: GameSnapshot, winner: str, reason: str) -> WinResult:
    winning_player_ids = [
        player.id
        for player in snapshot.players.values()
        if player.role is not None and faction_for_role(snapshot, player.role) == winner
    ]
    return WinResult(
        winner=winner,
        reason=reason,
        day=snapshot.day,
        winning_player_ids=winning_player_ids,
    )
