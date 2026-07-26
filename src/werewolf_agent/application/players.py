"""Player selection for create-game requirements."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from werewolf_agent.application.definitions import PlayerProfile, PlayerRoster
from werewolf_agent.application.errors import GameError
from werewolf_agent.application.messages import MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS

DEFAULT_PLAYER_NAME_PATTERN = re.compile(r"^Player\s+\d+$")


@dataclass(frozen=True)
class SelectedPlayerProfile:
    """One selected player profile for a game seat."""

    profile_id: str
    profile: PlayerProfile


def select_players(
    roster: PlayerRoster,
    *,
    player_count: int,
    seed: int | None,
) -> list[SelectedPlayerProfile]:
    """Select unique player profiles for one game."""
    candidates = sorted(roster.players.items())
    if player_count > len(candidates):
        raise GameError(
            MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS,
            context={"player_count": player_count, "roster_count": len(candidates)},
        )
    rng = random.Random(seed)
    return [
        SelectedPlayerProfile(profile_id=profile_id, profile=profile)
        for profile_id, profile in rng.sample(candidates, player_count)
    ]


def display_name_for(requested_name: str, selected_profile: SelectedPlayerProfile) -> str:
    """Return the requested custom name or the selected profile name."""
    if DEFAULT_PLAYER_NAME_PATTERN.fullmatch(requested_name.strip()):
        return selected_profile.profile.name
    return requested_name


def profile_ids_by_player(
    player_ids: list[str],
    selected_profiles: list[SelectedPlayerProfile],
) -> dict[str, str]:
    """Return profile ids keyed by stable game player id."""
    return {
        player_id: selected.profile_id
        for player_id, selected in zip(player_ids, selected_profiles, strict=True)
    }
