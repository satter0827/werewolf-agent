"""Provider-independent models for LLM style player decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import Field, field_validator, model_validator

from werewolf_agent.commons.shared.definitions import PlayerProfile as PlayerProfileDefinition
from werewolf_agent.commons.shared.messages import (
    MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD,
    MESSAGE_SPEECH_DECISION_FORBIDS_TARGET,
    MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE,
    message_message_not_allowed,
    message_target_required,
    message_unsupported_type,
)
from werewolf_agent.commons.shared.models import StrictModel
from werewolf_agent.commons.shared.validation import non_blank, optional_non_blank


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


class _LlmModel(StrictModel):
    """Base model for LLM domain values."""


class VisiblePlayer(_LlmModel):
    """Player information that may be shown to a decision provider."""

    id: str
    name: str
    status: AgentPlayerStatus

    @field_validator("id", "name")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return non_blank(value, str(info.field_name))


class _AgentSpeech(_LlmModel):
    """Public speech visible to a decision provider."""

    player_id: str
    message: str

    @field_validator("player_id", "message")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return non_blank(value, str(info.field_name))


class _AgentVoteRound(_LlmModel):
    """Public voting result visible to a decision provider."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    eliminated_player_id: str | None = None

    @field_validator("votes")
    @classmethod
    def validate_votes(cls, value: dict[str, str]) -> dict[str, str]:
        """Return votes with trimmed non-empty string keys and values."""
        return {
            non_blank(str(key), "vote_round voter id"): non_blank(item, "vote_round target id")
            for key, item in value.items()
        }

    @field_validator("counts")
    @classmethod
    def validate_counts(cls, value: dict[str, int]) -> dict[str, int]:
        """Return vote counts with trimmed non-empty string keys."""
        return {non_blank(str(key), "vote_round count key"): item for key, item in value.items()}

    @field_validator("eliminated_player_id")
    @classmethod
    def validate_optional_eliminated_player_id(cls, value: str | None) -> str | None:
        """Return a trimmed optional eliminated player id."""
        return optional_non_blank(value, "eliminated_player_id")


class PlayerProfile(PlayerProfileDefinition):
    """LLM-only player behavior profile."""


class AgentScenario(_LlmModel):
    """Public scenario premise visible to an agent decision provider."""

    name: str
    premise: str

    @field_validator("name", "premise")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return normalized scenario text."""
        return non_blank(value, str(info.field_name))


class AgentObservation(_LlmModel):
    """Provider-independent observation for one player decision."""

    phase: AgentPhase
    day: int
    me: VisiblePlayer
    role: str | None = None
    profile: PlayerProfile | None = None
    scenario: AgentScenario | None = None
    players: list[VisiblePlayer]
    known_roles: dict[str, str] = Field(default_factory=dict)
    available_actions: list[AgentActionType] = Field(default_factory=list)
    speeches: list[_AgentSpeech] = Field(default_factory=list)
    vote_rounds: list[_AgentVoteRound] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_optional_role(cls, value: str | None) -> str | None:
        """Return a trimmed optional role id."""
        return optional_non_blank(value, "role")

    @field_validator("known_roles")
    @classmethod
    def validate_known_roles(cls, value: dict[str, str]) -> dict[str, str]:
        """Return known role ids keyed by player id."""
        return {
            non_blank(str(player_id), "known role player id"): non_blank(role, "known role")
            for player_id, role in value.items()
        }


class PlayerProfileCatalog(_LlmModel):
    """LLM-only catalog of available player behavior profiles."""

    profiles: dict[str, PlayerProfile]

    @field_validator("profiles")
    @classmethod
    def validate_profiles(cls, value: dict[str, PlayerProfile]) -> dict[str, PlayerProfile]:
        """Return enabled agent profiles keyed by normalized profile id."""
        profiles = {
            non_blank(str(agent_id), "agent id"): profile
            for agent_id, profile in value.items()
            if profile.enabled
        }
        if not profiles:
            raise ValueError("profiles must include at least one enabled profile")
        return profiles

    def profile_for(self, profile_id: str | None) -> PlayerProfile:
        """Return a selected profile or the first enabled profile."""
        if profile_id is not None:
            return self.profiles[profile_id]
        first_id = sorted(self.profiles)[0]
        return self.profiles[first_id]


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
        return non_blank(value, "player_id")

    @field_validator("target_id", "message")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: Any) -> str | None:
        """Return a trimmed optional string."""
        return optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Ensure the decision payload matches the decision type."""
        if self.type is AgentActionType.SPEECH:
            if self.message is None:
                raise ValueError(MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE)
            if self.target_id is not None:
                raise ValueError(MESSAGE_SPEECH_DECISION_FORBIDS_TARGET)
            return self

        if self.type in self.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(message_target_required(self.type.value, "decisions"))
            if self.message is not None:
                raise ValueError(message_message_not_allowed(self.type.value, "decisions"))
            return self

        if self.type is AgentActionType.PASS:
            if self.target_id is not None or self.message is not None:
                raise ValueError(MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD)
            return self

        raise ValueError(message_unsupported_type(self.type.value, "decision"))

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
    "AgentScenario",
    "PlayerProfile",
    "PlayerProfileCatalog",
    "VisiblePlayer",
]
