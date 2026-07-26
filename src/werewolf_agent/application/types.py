"""Stable identifiers shared by application commands, records, and results."""

from typing import Annotated, Final, Literal

from pydantic import Field

GAME_STATUS_RUNNING: Final = "running"
GAME_STATUS_COMPLETED: Final = "completed"

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
Faction = Literal["village", "werewolf"]
Winner = Faction
RoleId = str
RoleCount = Annotated[int, Field(ge=0)]

__all__ = [
    "GAME_STATUS_COMPLETED",
    "GAME_STATUS_RUNNING",
    "Faction",
    "GamePhase",
    "GameStatus",
    "RoleCount",
    "RoleId",
    "Winner",
]
