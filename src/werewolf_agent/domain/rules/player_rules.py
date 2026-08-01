"""Player state, faction, and win-condition rules."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

from werewolf_agent.domain._messages import (
    message_expected_phase,
    message_player_not_alive,
    message_unknown_player_id,
)
from werewolf_agent.domain.errors import GameError, GamePhaseError
from werewolf_agent.domain.state import (
    FACTION_FOX,
    FACTION_VILLAGE,
    FACTION_WEREWOLF,
    DeathReaction,
    DeathReactionResolution,
    GameState,
    Phase,
    Player,
    PlayerStatus,
    WinResult,
)

if TYPE_CHECKING:
    from werewolf_agent.domain.rule_packs import AbilityPolicy


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
    policy: AbilityPolicy,
    during_night: bool,
) -> tuple[GameState, tuple[str, ...]]:
    """Policy Outcomeを検証し、連鎖死亡と使用回数をatomicに適用する."""
    random_state = rng.getstate()
    try:
        resolution = policy.resolve_death_reactions(
            snapshot,
            tuple(newly_dead_player_ids),
            rng,
        )
        return _apply_death_reaction_resolution(
            snapshot,
            newly_dead_player_ids,
            resolution,
            during_night=during_night,
        )
    except Exception:
        rng.setstate(random_state)
        raise


def resolve_core_death_reactions(
    snapshot: GameState,
    newly_dead_player_ids: tuple[str, ...],
    rng: random.Random,
) -> DeathReactionResolution:
    """組み込みの決定的な死亡反応連鎖をstate変更なしで計算する."""
    alive_ids = {player.id for player in alive_players(snapshot)}
    queue = list(newly_dead_player_ids)
    reactions: list[DeathReaction] = []
    pending_uses: Counter[tuple[str, str]] = Counter()
    while queue:
        dead_id = queue.pop(0)
        dead = snapshot.players[dead_id]
        if dead.role is None:
            continue
        role = snapshot.config.roles.require_role(dead.role)
        reaction_abilities = sorted(
            (
                ability_id
                for ability_id in role.abilities
                if _death_reaction_is_enabled(
                    snapshot,
                    dead_id,
                    ability_id,
                    pending_uses=pending_uses,
                )
            ),
            key=lambda ability_id: (
                snapshot.config.abilities[ability_id].resolution_priority,
                ability_id,
            ),
        )
        for ability_id in reaction_abilities:
            targets = sorted(alive_ids)
            if not targets:
                break
            target_id = rng.choice(targets)
            alive_ids.remove(target_id)
            pending_uses[(dead_id, ability_id)] += 1
            reactions.append(DeathReaction(dead_id, ability_id, target_id))
            queue.append(target_id)
    return DeathReactionResolution(tuple(reactions))


def _apply_death_reaction_resolution(
    snapshot: GameState,
    newly_dead_player_ids: list[str],
    resolution: DeathReactionResolution,
    *,
    during_night: bool,
) -> tuple[GameState, tuple[str, ...]]:
    """検証済み死亡反応を順序どおりGameStateへ適用する."""
    if not isinstance(resolution, DeathReactionResolution):
        raise TypeError("ability policy must return DeathReactionResolution")
    updated = snapshot
    dead_ids = set(newly_dead_player_ids)
    reaction_deaths: list[str] = []
    resolved_abilities: set[tuple[str, str]] = set()
    for reaction in resolution.reactions:
        if reaction.player_id not in dead_ids:
            raise ValueError("death reaction owner must already be dead")
        owner = updated.players[reaction.player_id]
        if owner.role is None:
            raise ValueError("death reaction owner must have a role")
        role = updated.config.roles.require_role(owner.role)
        if reaction.ability_id not in role.abilities:
            raise ValueError("death reaction ability must belong to its owner")
        ability_key = (reaction.player_id, reaction.ability_id)
        if ability_key in resolved_abilities:
            raise ValueError("death reaction ability can resolve only once")
        if not _death_reaction_is_enabled(
            updated,
            reaction.player_id,
            reaction.ability_id,
        ):
            raise ValueError("death reaction ability is not enabled")
        require_alive(updated, reaction.target_id)
        resolved_abilities.add(ability_key)
        updated = _consume_passive_use(updated, reaction.player_id, reaction.ability_id)
        updated = mark_dead(
            updated,
            reaction.target_id,
            killed_night=updated.day if during_night else None,
            eliminated_day=None if during_night else updated.day,
        )
        reaction_deaths.append(reaction.target_id)
        dead_ids.add(reaction.target_id)
    return updated, tuple(reaction_deaths)


def _death_reaction_is_enabled(
    snapshot: GameState,
    player_id: str,
    ability_id: str,
    *,
    pending_uses: Counter[tuple[str, str]] | None = None,
) -> bool:
    ability = snapshot.config.abilities[ability_id]
    used = snapshot.ability_uses.get(player_id, {}).get(ability_id, 0)
    if pending_uses is not None:
        used += pending_uses[(player_id, ability_id)]
    return (
        ability.kind == "death_reaction"
        and ability.phase is snapshot.phase
        and snapshot.day >= ability.start_day
        and (snapshot.day != 1 or snapshot.phase is not Phase.NIGHT or ability.enabled_first_night)
        and (ability.max_uses is None or used < ability.max_uses)
    )


def _consume_passive_use(snapshot: GameState, player_id: str, ability_id: str) -> GameState:
    ability = snapshot.config.abilities[ability_id]
    if ability.max_uses is None:
        return snapshot
    uses = {key: dict(value) for key, value in snapshot.ability_uses.items()}
    player_uses = uses.setdefault(player_id, {})
    player_uses[ability_id] = player_uses.get(ability_id, 0) + 1
    return replace(snapshot, ability_uses=uses)


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
