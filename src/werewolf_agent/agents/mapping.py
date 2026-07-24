"""Conversions from configured player profiles to agent models."""

from werewolf_agent.agents.models import PlayerProfile, PlayerProfileCatalog
from werewolf_agent.configuration.definitions import PlayerRoster


def to_player_profiles(definitions: PlayerRoster) -> PlayerProfileCatalog:
    """Convert configured player profiles into provider-independent values."""
    return PlayerProfileCatalog(
        profiles={
            profile_id: PlayerProfile.model_validate(definition.model_dump(mode="json"))
            for profile_id, definition in definitions.players.items()
        }
    )
