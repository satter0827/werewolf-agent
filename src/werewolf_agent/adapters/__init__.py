"""External service adapters and client ports."""

from werewolf_agent.adapters.factory import build_game_client
from werewolf_agent.adapters.ports import GameClient

__all__ = ["GameClient", "build_game_client"]
