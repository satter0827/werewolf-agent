"""Visibility-filtered observation rules."""

from __future__ import annotations

from werewolf_agent.domain.rules.action_availability import available_actions, legal_targets
from werewolf_agent.domain.rules.player_rules import player_by_id
from werewolf_agent.domain.state import (
    AbilityDefinition,
    GameHistory,
    GameState,
    GameView,
    PendingActions,
    Phase,
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
    known_factions = _known_factions(snapshot, player_id, known_roles)
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
        known_factions=known_factions,
        available_actions=tuple(available_actions(snapshot, pending_actions, player_id)),
        legal_targets={
            key: tuple(targets)
            for key, targets in legal_targets(snapshot, pending_actions, player_id).items()
        },
        history=GameHistory(speeches=snapshot.history.speeches, votes=snapshot.history.votes),
        win_result=snapshot.win_result,
    )


def _role_abilities(
    snapshot: GameState, player_id: str, kind: str
) -> list[tuple[str, AbilityDefinition]]:
    player = player_by_id(snapshot, player_id)
    if player.role is None:
        return []
    role = snapshot.config.roles.require_role(player.role)
    return [
        (ability_id, snapshot.config.abilities[ability_id])
        for ability_id in role.abilities
        if snapshot.config.abilities[ability_id].kind == kind
    ]


def _known_roles(snapshot: GameState, player_id: str) -> dict[str, str]:
    observer = player_by_id(snapshot, player_id)
    known: dict[str, str] = {}
    if observer.role is not None:
        known[observer.id] = observer.role

    for owner_id, ability in _visible_knowledge(snapshot, player_id):
        owner = player_by_id(snapshot, owner_id)
        if (
            ability.knowledge_mode == "allies"
            and ability.result_detail == "role"
            and owner.role is not None
        ):
            faction = snapshot.config.roles.faction_for_role(owner.role)
            for player in snapshot.players.values():
                if (
                    player.role is not None
                    and snapshot.config.roles.faction_for_role(player.role) == faction
                ):
                    known[player.id] = player.role
        if ability.knowledge_mode == "last_eliminated" and ability.result_detail == "role":
            for vote in snapshot.history.votes:
                if vote.eliminated_player_id is not None:
                    target = snapshot.players[vote.eliminated_player_id]
                    if target.role is not None:
                        known[target.id] = target.role

    for night in snapshot.history.nights:
        for inspection in night.inspections:
            ability = snapshot.config.abilities[inspection.ability_id]
            if (
                _can_see_ability_result(ability, inspection.player_id, player_id)
                and ability.result_detail == "role"
            ):
                known[inspection.target_id] = inspection.target_role
    if snapshot.config.rules.reveal_role_on_death:
        for player in snapshot.players.values():
            if not player.is_alive and player.role is not None:
                known[player.id] = player.role
    return known


def _known_factions(
    snapshot: GameState,
    player_id: str,
    known_roles: dict[str, str],
) -> dict[str, str]:
    known = {
        target_id: snapshot.config.roles.faction_for_role(role)
        for target_id, role in known_roles.items()
    }
    for night in snapshot.history.nights:
        for inspection in night.inspections:
            ability = snapshot.config.abilities[inspection.ability_id]
            if _can_see_ability_result(ability, inspection.player_id, player_id):
                known[inspection.target_id] = inspection.target_faction
    for owner_id, ability in _visible_knowledge(snapshot, player_id):
        owner = player_by_id(snapshot, owner_id)
        if ability.knowledge_mode == "allies" and owner.role is not None:
            faction = snapshot.config.roles.faction_for_role(owner.role)
            for player in snapshot.players.values():
                if (
                    player.role is not None
                    and snapshot.config.roles.faction_for_role(player.role) == faction
                ):
                    known[player.id] = faction
        if ability.knowledge_mode != "last_eliminated":
            continue
        for vote in snapshot.history.votes:
            if vote.eliminated_player_id is None:
                continue
            target = snapshot.players[vote.eliminated_player_id]
            if target.role is not None:
                known[target.id] = snapshot.config.roles.faction_for_role(target.role)
    return known


def _visible_knowledge(
    snapshot: GameState,
    observer_player_id: str,
) -> list[tuple[str, AbilityDefinition]]:
    visible: list[tuple[str, AbilityDefinition]] = []
    for owner in snapshot.players.values():
        if owner.role is None:
            continue
        for _, ability in _role_abilities(snapshot, owner.id, "knowledge"):
            if _ability_has_started(snapshot, ability) and _can_see_ability_result(
                ability,
                owner.id,
                observer_player_id,
            ):
                visible.append((owner.id, ability))
    return visible


def _ability_has_started(snapshot: GameState, ability: AbilityDefinition) -> bool:
    if snapshot.day < ability.start_day:
        return False
    if ability.phase is Phase.NIGHT and snapshot.day == 1 and not ability.enabled_first_night:
        return False
    if snapshot.day > ability.start_day or snapshot.phase is Phase.FINISHED:
        return True
    if ability.phase is Phase.FINISHED:
        return False
    return snapshot.config.phase_order.index(snapshot.phase) >= snapshot.config.phase_order.index(
        ability.phase
    )


def _can_see_ability_result(
    ability: AbilityDefinition,
    owner_player_id: str,
    observer_player_id: str,
) -> bool:
    if ability.result_visibility == "public":
        return True
    return ability.result_visibility == "private" and owner_player_id == observer_player_id
