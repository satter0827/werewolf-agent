"""Initial game-state construction rules."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Sequence

from werewolf_agent.commons.shared.messages import (
    MESSAGE_EXPLICIT_ROLES_MUST_MATCH_ROLE_COUNTS,
    MESSAGE_PLAYER_IDS_MUST_BE_UNIQUE,
    MESSAGE_PLAYER_LIST_LENGTH_MUST_MATCH_CONFIG,
    MESSAGE_PLAYER_ROLES_ALL_OR_NONE,
)
from werewolf_agent.contracts import GameError
from werewolf_agent.domain.game.models import GameConfig, GameSnapshot, Phase, Player, Role


def create_game_snapshot(
    config: GameConfig,
    players: Sequence[Player],
    rng: random.Random,
) -> GameSnapshot:
    """Return a validated initial game snapshot."""
    if len(players) != config.player_count:
        raise GameError(
            MESSAGE_PLAYER_LIST_LENGTH_MUST_MATCH_CONFIG,
            context={"player_count": config.player_count, "players": len(players)},
        )
    _ensure_unique_player_ids(players)
    assigned_roles = _assign_roles(config, players, rng)
    player_states = {
        player.id: Player(
            id=player.id,
            name=player.name,
            role=role,
            status=player.status,
            eliminated_day=player.eliminated_day,
            killed_night=player.killed_night,
        )
        for player, role in zip(players, assigned_roles, strict=True)
    }
    return GameSnapshot(
        game_id=config.game_id,
        config=config,
        phase=Phase.NIGHT,
        day=1,
        players=player_states,
    )


def _ensure_unique_player_ids(players: Sequence[Player]) -> None:
    player_ids = [player.id for player in players]
    duplicate_ids = sorted(
        player_id for player_id, count in Counter(player_ids).items() if count > 1
    )
    if duplicate_ids:
        raise GameError(
            MESSAGE_PLAYER_IDS_MUST_BE_UNIQUE,
            context={"duplicate_player_ids": duplicate_ids},
        )


def _assign_roles(
    config: GameConfig,
    players: Sequence[Player],
    rng: random.Random,
) -> list[Role]:
    explicit_roles = [player.role for player in players]
    if any(role is not None for role in explicit_roles):
        if any(role is None for role in explicit_roles):
            raise GameError(MESSAGE_PLAYER_ROLES_ALL_OR_NONE)
        assigned_roles = [role for role in explicit_roles if role is not None]
        if Counter(assigned_roles) != Counter(config.role_counts):
            raise GameError(
                MESSAGE_EXPLICIT_ROLES_MUST_MATCH_ROLE_COUNTS,
                context={
                    "expected_role_counts": {
                        role.value: count for role, count in config.role_counts.items()
                    },
                    "actual_role_counts": {
                        role.value: count for role, count in Counter(assigned_roles).items()
                    },
                },
            )
        return assigned_roles

    roles: list[Role] = []
    for role, count in sorted(config.role_counts.items(), key=lambda item: item[0].value):
        roles.extend([role] * count)
    rng.shuffle(roles)
    return roles
