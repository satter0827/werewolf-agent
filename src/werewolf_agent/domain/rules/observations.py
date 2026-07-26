"""Visibility-filtered observation rules."""

from __future__ import annotations

from werewolf_agent.domain.rules.action_availability import available_actions, legal_targets
from werewolf_agent.domain.rules.player_rules import player_by_id
from werewolf_agent.domain.state import (
    ABILITY_PACK_KNOWLEDGE,
    FACTION_WEREWOLF,
    GameHistory,
    GameState,
    GameView,
    PendingActions,
    Player,
)


def build_player_observation(
    snapshot: GameState,
    pending_actions: PendingActions,
    player_id: str,
) -> GameView:
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
    return GameView(
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
        players=tuple(observed_players),
        known_roles=known_roles,
        available_actions=tuple(available_actions(snapshot, pending_actions, player_id)),
        legal_targets={
            action_type: tuple(targets)
            for action_type, targets in legal_targets(snapshot, pending_actions, player_id).items()
        },
        history=GameHistory(
            speeches=snapshot.history.speeches,
            votes=snapshot.history.votes,
        ),
        win_result=snapshot.win_result,
    )


def _known_roles(snapshot: GameState, player_id: str) -> dict[str, str]:
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
