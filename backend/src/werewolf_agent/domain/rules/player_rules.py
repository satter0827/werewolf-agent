"""Player state, faction, and win-condition rules."""

from __future__ import annotations

from werewolf_agent.contracts import GameError, GamePhaseError
from werewolf_agent.domain.models import (
    Faction,
    GameSnapshot,
    Phase,
    Player,
    PlayerStatus,
    Role,
    WinResult,
)


def faction_for_role(role: Role) -> Faction:
    """Return the faction for one role."""
    if role is Role.WEREWOLF:
        return Faction.WEREWOLF
    return Faction.VILLAGE


def require_phase(snapshot: GameSnapshot, expected: Phase) -> None:
    """Raise if the game is not in the expected phase."""
    if snapshot.phase is not expected:
        raise GamePhaseError(
            f"Expected phase {expected.value}, but current phase is {snapshot.phase.value}.",
            context={"expected_phase": expected.value, "current_phase": snapshot.phase.value},
        )


def player_by_id(snapshot: GameSnapshot, player_id: str) -> Player:
    """Return one player or raise a safe game error."""
    try:
        return snapshot.players[player_id]
    except KeyError as exc:
        raise GameError(
            f"Unknown player id: {player_id}.",
            context={"player_id": player_id},
        ) from exc


def require_alive(snapshot: GameSnapshot, player_id: str) -> Player:
    """Return one alive player or raise a safe game error."""
    player = player_by_id(snapshot, player_id)
    if player.status is not PlayerStatus.ALIVE:
        raise GameError(
            f"Player is not alive: {player_id}.",
            context={"player_id": player_id, "status": player.status.value},
        )
    return player


def require_role(snapshot: GameSnapshot, player_id: str, expected: Role) -> Player:
    """Return an alive player with the expected role."""
    player = require_alive(snapshot, player_id)
    if player.role is not expected:
        actual_role = player.role.value if player.role is not None else None
        raise GameError(
            f"Player {player_id} cannot perform a {expected.value} action.",
            context={
                "player_id": player_id,
                "expected_role": expected.value,
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
    alive_wolves = [player for player in alive if player.role is Role.WEREWOLF]
    alive_village = [player for player in alive if player.role is not Role.WEREWOLF]

    if not alive_wolves:
        return _win_result(snapshot, Faction.VILLAGE, "all_werewolves_eliminated")
    if len(alive_wolves) >= len(alive_village):
        return _win_result(snapshot, Faction.WEREWOLF, "werewolves_reached_parity")
    return None


def _win_result(snapshot: GameSnapshot, winner: Faction, reason: str) -> WinResult:
    winning_player_ids = [
        player.id
        for player in snapshot.players.values()
        if player.role is not None and faction_for_role(player.role) is winner
    ]
    return WinResult(
        winner=winner,
        reason=reason,
        day=snapshot.day,
        winning_player_ids=winning_player_ids,
    )
