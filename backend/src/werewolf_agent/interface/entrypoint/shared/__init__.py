"""Shared helpers for user-facing entry points."""

from werewolf_agent.interface.entrypoint.shared.client import GameApiClient, HttpGameApiClient
from werewolf_agent.interface.entrypoint.shared.requests import (
    build_create_game_request,
    parse_role_counts,
)

__all__ = [
    "GameApiClient",
    "HttpGameApiClient",
    "build_create_game_request",
    "parse_role_counts",
]
