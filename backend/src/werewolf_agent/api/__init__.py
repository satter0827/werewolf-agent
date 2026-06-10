"""Public game API surface for entry points."""

from werewolf_agent.api.factory import build_game_api
from werewolf_agent.api.ports import GameApi

__all__ = ["GameApi", "build_game_api"]
