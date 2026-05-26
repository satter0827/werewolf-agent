"""Visibility-filtered observations for agents."""

from __future__ import annotations

from werewolf_agent.domain._rules import player_by_id
from werewolf_agent.domain.models import (
    GameSnapshot,
    Observation,
    ObservedPlayer,
    Phase,
    PlayerStatus,
    Role,
)


def build_observation(snapshot: GameSnapshot, player_id: str) -> Observation:
    """Return the information visible to one player."""
    observer = player_by_id(snapshot, player_id)
    known_roles = _known_roles(snapshot, player_id)
    observed_players = [
        ObservedPlayer(
            player_id=player.player_id,
            name=player.name,
            status=player.status,
            role=known_roles.get(player.player_id),
        )
        for player in snapshot.players.values()
    ]
    return Observation(
        player_id=player_id,
        phase=snapshot.phase,
        day=snapshot.day,
        self_player=ObservedPlayer(
            player_id=observer.player_id,
            name=observer.name,
            status=observer.status,
            role=observer.role,
        ),
        players=observed_players,
        known_roles=known_roles,
        available_actions=_available_actions(snapshot, player_id),
        speeches=snapshot.speeches,
        vote_history=snapshot.vote_history,
        win_result=snapshot.win_result,
    )


def _known_roles(snapshot: GameSnapshot, player_id: str) -> dict[str, Role]:
    observer = player_by_id(snapshot, player_id)
    known_roles = {observer.player_id: observer.role}

    if observer.role is Role.WEREWOLF:
        for player in snapshot.players.values():
            if player.role is Role.WEREWOLF:
                known_roles[player.player_id] = player.role

    for night_result in snapshot.night_history:
        for inspection in night_result.inspections:
            if inspection.seer_id == player_id:
                known_roles[inspection.target_id] = inspection.target_role
    return known_roles


def _available_actions(snapshot: GameSnapshot, player_id: str) -> list[str]:
    observer = player_by_id(snapshot, player_id)
    if observer.status is not PlayerStatus.ALIVE:
        return []
    if snapshot.phase is Phase.DAY_DISCUSSION:
        return ["speech"]
    if snapshot.phase is Phase.VOTING:
        return ["vote"]
    if snapshot.phase is Phase.NIGHT:
        if observer.role is Role.WEREWOLF:
            return ["werewolf_attack"]
        if observer.role is Role.SEER:
            return ["seer_inspect"]
        if observer.role is Role.KNIGHT:
            return ["knight_guard"]
    return []
