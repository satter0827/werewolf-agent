"""Provider-independent models for LLM style player decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentRole(StrEnum):
    """Roles visible to a player decision provider."""

    VILLAGER = "villager"
    WEREWOLF = "werewolf"
    SEER = "seer"
    KNIGHT = "knight"


class AgentPhase(StrEnum):
    """Game phases visible to a player decision provider."""

    SETUP = "setup"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    FINISHED = "finished"


class AgentPlayerStatus(StrEnum):
    """Player life state visible to a player decision provider."""

    ALIVE = "alive"
    DEAD = "dead"


class AgentActionType(StrEnum):
    """Structured decision types emitted by a player decision provider."""

    SPEECH = "speech"
    VOTE = "vote"
    WEREWOLF_ATTACK = "werewolf_attack"
    SEER_INSPECT = "seer_inspect"
    KNIGHT_GUARD = "knight_guard"
    PASS = "pass"


class _LlmModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _non_blank(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)
    return normalized


def _optional_non_blank(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_blank(value, field_name)


class VisiblePlayer(_LlmModel):
    """Player information that may be shown to a decision provider."""

    id: str
    name: str
    status: AgentPlayerStatus

    @field_validator("id", "name")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class AgentObservation(_LlmModel):
    """Provider-independent observation for one player decision."""

    phase: AgentPhase
    day: int
    me: VisiblePlayer
    role: AgentRole | None = None
    players: list[VisiblePlayer]
    known_roles: dict[str, AgentRole] = Field(default_factory=dict)
    available_actions: list[AgentActionType] = Field(default_factory=list)


class AgentDecision(_LlmModel):
    """Structured decision returned by a player decision provider."""

    type: AgentActionType
    player_id: str
    target_id: str | None = None
    message: str | None = None
    reason: str = ""

    TARGET_TYPES: ClassVar[frozenset[AgentActionType]] = frozenset(
        {
            AgentActionType.VOTE,
            AgentActionType.WEREWOLF_ATTACK,
            AgentActionType.SEER_INSPECT,
            AgentActionType.KNIGHT_GUARD,
        }
    )

    @field_validator("player_id")
    @classmethod
    def validate_player_id(cls, value: str) -> str:
        """Return a trimmed non-empty player id."""
        return _non_blank(value, "player_id")

    @field_validator("target_id", "message")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: Any) -> str | None:
        """Return a trimmed optional string."""
        return _optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Ensure the decision payload matches the decision type."""
        if self.type is AgentActionType.SPEECH:
            if self.message is None:
                raise ValueError("message is required for speech decisions")
            if self.target_id is not None:
                raise ValueError("target_id is not allowed for speech decisions")
            return self

        if self.type in self.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(f"target_id is required for {self.type.value} decisions")
            if self.message is not None:
                raise ValueError(f"message is not allowed for {self.type.value} decisions")
            return self

        if self.type is AgentActionType.PASS:
            if self.target_id is not None or self.message is not None:
                raise ValueError("pass decisions cannot include target_id or message")
            return self

        raise ValueError(f"unsupported decision type: {self.type.value}")

    @classmethod
    def speech(cls, player_id: str, message: str) -> Self:
        """Create a speech decision."""
        return cls(type=AgentActionType.SPEECH, player_id=player_id, message=message)

    @classmethod
    def vote(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a vote decision."""
        return cls(
            type=AgentActionType.VOTE,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def attack(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a werewolf attack decision."""
        return cls(
            type=AgentActionType.WEREWOLF_ATTACK,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def inspect(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a seer inspection decision."""
        return cls(
            type=AgentActionType.SEER_INSPECT,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def guard(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a knight guard decision."""
        return cls(
            type=AgentActionType.KNIGHT_GUARD,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def pass_(cls, player_id: str, *, reason: str = "") -> Self:
        """Create a structured no-op decision."""
        return cls(type=AgentActionType.PASS, player_id=player_id, reason=reason)


__all__ = [
    "AgentActionType",
    "AgentDecision",
    "AgentObservation",
    "AgentPhase",
    "AgentPlayerStatus",
    "AgentRole",
    "VisiblePlayer",
]
