"""Visibility-filtered observation rules."""

from __future__ import annotations

from werewolf_agent.domain.game.models import (
    ABILITY_PACK_KNOWLEDGE,
    FACTION_WEREWOLF,
    GameHistory,
    GameSnapshot,
    Observation,
    PendingActions,
    Player,
)
from werewolf_agent.domain.game.rules.action_availability import available_actions
from werewolf_agent.domain.game.rules.player_rules import player_by_id


def build_player_observation(
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    player_id: str,
) -> Observation:
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
        available_actions=available_actions(snapshot, pending_actions, player_id),
        history=GameHistory(
            speeches=snapshot.history.speeches,
            votes=snapshot.history.votes,
        ),
        win_result=snapshot.win_result,
    )


def _known_roles(snapshot: GameSnapshot, player_id: str) -> dict[str, str]:
    observer = player_by_id(snapshot, player_id)
    known_roles: dict[str, str] = {}
    if observer.role is not None:
        known_roles[observer.id] = observer.role

    if snapshot.config.roles.role_has_ability(observer.role, ABILITY_PACK_KNOWLEDGE):
        for player in snapshot.players.values():
            if (
                player.role is not None
                and snapshot.config.roles.faction_for_role(player.role) == FACTION_WEREWOLF
            ):
                known_roles[player.id] = player.role

    for night_result in snapshot.history.nights:
        for inspection in night_result.inspections:
            if inspection.seer_id == player_id:
                known_roles[inspection.target_id] = inspection.target_role
    return known_roles
