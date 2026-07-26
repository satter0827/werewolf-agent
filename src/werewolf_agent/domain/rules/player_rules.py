"""Player state, faction, and win-condition rules."""

from __future__ import annotations

import random
from dataclasses import replace

from werewolf_agent.domain._messages import (
    message_expected_phase,
    message_player_cannot_perform_role_action,
    message_player_not_alive,
    message_unknown_player_id,
)
from werewolf_agent.domain.errors import GameError, GamePhaseError
from werewolf_agent.domain.state import (
    ABILITY_DEATH_SHOT,
    FACTION_FOX,
    FACTION_VILLAGE,
    FACTION_WEREWOLF,
    GameState,
    Phase,
    Player,
    PlayerStatus,
    WinResult,
)


def faction_for_role(snapshot: GameState, role: str) -> str:
    """Return the faction for one role."""
    return snapshot.config.roles.faction_for_role(role)


def require_phase(snapshot: GameState, expected: Phase) -> None:
    """Raise if the game is not in the expected phase."""
    if snapshot.phase is not expected:
        raise GamePhaseError(
            message_expected_phase(expected.value, snapshot.phase.value),
            context={"expected_phase": expected.value, "current_phase": snapshot.phase.value},
        )


def player_by_id(snapshot: GameState, player_id: str) -> Player:
    """Return one player or raise a safe game error."""
    try:
        return snapshot.players[player_id]
    except KeyError as exc:
        raise GameError(
            message_unknown_player_id(player_id),
            context={"player_id": player_id},
        ) from exc


def require_alive(snapshot: GameState, player_id: str) -> Player:
    """Return one alive player or raise a safe game error."""
    player = player_by_id(snapshot, player_id)
    if player.status is not PlayerStatus.ALIVE:
        raise GameError(
            message_player_not_alive(player_id),
            context={"player_id": player_id, "status": player.status.value},
        )
    return player


def require_role(snapshot: GameState, player_id: str, expected: str) -> Player:
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


def alive_players(snapshot: GameState) -> list[Player]:
    """Return alive players in stable game order."""
    return [player for player in snapshot.players.values() if player.status is PlayerStatus.ALIVE]


def mark_dead(
    snapshot: GameState,
    player_id: str,
    *,
    eliminated_day: int | None = None,
    killed_night: int | None = None,
) -> GameState:
    """Return a copy of the snapshot with one player marked dead."""
    player = require_alive(snapshot, player_id)
    updated_player = replace(
        player,
        status=PlayerStatus.DEAD,
        eliminated_day=eliminated_day,
        killed_night=killed_night,
    )
    updated_players = dict(snapshot.players)
    updated_players[player_id] = updated_player
    return replace(snapshot, players=updated_players)


def resolve_death_reactions(
    snapshot: GameState,
    newly_dead_player_ids: list[str],
    rng: random.Random,
    *,
    during_night: bool,
) -> tuple[GameState, tuple[str, ...]]:
    """Resolve passive hunter reactions, including deterministic chained deaths."""
    updated = snapshot
    queue = list(newly_dead_player_ids)
    reaction_deaths: list[str] = []
    while queue:
        dead_id = queue.pop(0)
        dead = updated.players[dead_id]
        if not updated.config.roles.role_has_ability(dead.role, ABILITY_DEATH_SHOT):
            continue
        targets = sorted(player.id for player in alive_players(updated))
        if not targets:
            continue
        target_id = rng.choice(targets)
        updated = mark_dead(
            updated,
            target_id,
            killed_night=updated.day if during_night else None,
            eliminated_day=None if during_night else updated.day,
        )
        reaction_deaths.append(target_id)
        queue.append(target_id)
    return updated, tuple(reaction_deaths)


def check_win(snapshot: GameState) -> WinResult | None:
    """Return a win result when either faction has met its win condition."""
    alive = alive_players(snapshot)
    alive_wolves = [
        player
        for player in alive
        if player.role is not None and faction_for_role(snapshot, player.role) == FACTION_WEREWOLF
    ]
    alive_non_wolves = [
        player
        for player in alive
        if player.role is not None and faction_for_role(snapshot, player.role) != FACTION_WEREWOLF
    ]

    if not alive_wolves:
        normal_winner = (FACTION_VILLAGE, "all_werewolves_eliminated")
    elif len(alive_wolves) >= len(alive_non_wolves):
        normal_winner = (FACTION_WEREWOLF, "werewolves_reached_parity")
    else:
        return None
    alive_foxes = [
        player
        for player in alive
        if player.role is not None
        and snapshot.config.roles.victory_team_for_role(player.role) == FACTION_FOX
    ]
    if alive_foxes:
        return _win_result(snapshot, FACTION_FOX, "fox_survived_until_normal_victory")
    return _win_result(snapshot, *normal_winner)


def _win_result(snapshot: GameState, winner: str, reason: str) -> WinResult:
    winning_player_ids = [
        player.id
        for player in snapshot.players.values()
        if player.role is not None
        and snapshot.config.roles.victory_team_for_role(player.role) == winner
    ]
    return WinResult(
        winner=winner,
        reason=reason,
        day=snapshot.day,
        winning_player_ids=tuple(winning_player_ids),
    )
