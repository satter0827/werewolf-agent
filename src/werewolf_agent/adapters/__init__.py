"""External service adapters and client ports."""

from werewolf_agent.adapters.factory import (
    build_admin_client,
    build_game_client,
    build_public_client,
)
from werewolf_agent.adapters.ports import AdminClient, GameClient, PublicClient

__all__ = [
    "AdminClient",
    "GameClient",
    "PublicClient",
    "build_admin_client",
    "build_game_client",
    "build_public_client",
]
