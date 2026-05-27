"""Visibility-filtered observation rules."""

from __future__ import annotations

from werewolf_agent.domain.game.models import (
    ActionType,
    GameHistory,
    GameSnapshot,
    Observation,
    Phase,
    Player,
    PlayerStatus,
    Role,
)
from werewolf_agent.domain.game.rules.player_rules import player_by_id


def build_player_observation(snapshot: GameSnapshot, player_id: str) -> Observation:
    """Return the information visible to one player."""
    observer = player_by_id(snapshot, player_id)
    known_roles = _known_roles(snapshot, player_id)
    observed_players = [
        Player(
            id=player.id,
            name=player.name,
            status=player.status,
            role=known_roles.get(player.id),
            eliminated_day=player.eliminated_day,
            killed_night=player.killed_night,
        )
        for player in snapshot.players.values()
    ]
    return Observation(
        phase=snapshot.phase,
        day=snapshot.day,
        me=Player(
            id=observer.id,
            name=observer.name,
            status=observer.status,
            role=observer.role,
            eliminated_day=observer.eliminated_day,
            killed_night=observer.killed_night,
        ),
        players=observed_players,
        known_roles=known_roles,
        available_actions=_available_actions(snapshot, player_id),
        history=GameHistory(
            speeches=snapshot.history.speeches,
            votes=snapshot.history.votes,
        ),
        win_result=snapshot.win_result,
    )


def _known_roles(snapshot: GameSnapshot, player_id: str) -> dict[str, Role]:
    observer = player_by_id(snapshot, player_id)
    known_roles: dict[str, Role] = {}
    if observer.role is not None:
        known_roles[observer.id] = observer.role

    if observer.role is Role.WEREWOLF:
        for player in snapshot.players.values():
            if player.role is Role.WEREWOLF:
                known_roles[player.id] = player.role

    for night_result in snapshot.history.nights:
        for inspection in night_result.inspections:
            if inspection.seer_id == player_id:
                known_roles[inspection.target_id] = inspection.target_role
    return known_roles


def _available_actions(snapshot: GameSnapshot, player_id: str) -> list[ActionType]:
    observer = player_by_id(snapshot, player_id)
    if observer.status is not PlayerStatus.ALIVE:
        return []
    if snapshot.phase is Phase.DAY_DISCUSSION:
        return [ActionType.SPEECH]
    if snapshot.phase is Phase.VOTING:
        return [ActionType.VOTE]
    if snapshot.phase is Phase.NIGHT:
        if observer.role is Role.WEREWOLF:
            return [ActionType.WEREWOLF_ATTACK]
        if observer.role is Role.SEER:
            return [ActionType.SEER_INSPECT]
        if observer.role is Role.KNIGHT:
            return [ActionType.KNIGHT_GUARD]
    return []
