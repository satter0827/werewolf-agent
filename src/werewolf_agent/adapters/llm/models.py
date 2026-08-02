"""Provider-independent models for automated player decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.adapters.llm.definitions import PlayerProfile as PlayerProfileDefinition
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_AGENT_PROFILES_REQUIRED,
    MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD,
    MESSAGE_SPEECH_DECISION_FORBIDS_TARGET,
    MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE,
    message_message_not_allowed,
    message_target_required,
    message_unsupported_type,
)
from werewolf_agent.agents.validation import non_blank, optional_non_blank


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
    USE_ABILITY = "use_ability"
    PASS = "pass"


class AgentDiscussionPosition(StrEnum):
    """Provider非依存の議論対象への立場."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    UNDECIDED = "undecided"


class AgentDiscussionRelation(StrEnum):
    """Provider非依存の参照発言との関係."""

    INDEPENDENT = "independent"
    ANSWER = "answer"
    SUPPORT = "support"
    CHALLENGE = "challenge"
    REVISE = "revise"


class DeliberationLevel(StrEnum):
    """Bounded context depth selected for one game."""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class _LlmModel(BaseModel):
    """Base model for LLM domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentAvailableAction(_LlmModel):
    """One concrete action option exposed to a decision provider."""

    type: AgentActionType
    ability_id: str | None = None

    @property
    def key(self) -> str:
        """Return the stable action key including an optional ability ID."""
        return f"{self.type.value}:{self.ability_id}" if self.ability_id else self.type.value

    @model_validator(mode="after")
    def validate_ability(self) -> Self:
        """Require an ability ID only for ability actions."""
        if (self.type is AgentActionType.USE_ABILITY) != (self.ability_id is not None):
            raise ValueError("use_abilityだけがability_idを持ちます")
        return self


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


class AgentSpeech(_LlmModel):
    """Public speech visible to a decision provider."""

    day: int = Field(ge=1)
    speech_id: str
    player_id: str
    utterance: str
    topic_id: str
    position: AgentDiscussionPosition
    relation: AgentDiscussionRelation
    evidence_id: str | None = None
    response_to_id: str | None = None

    @field_validator("speech_id", "player_id", "utterance", "topic_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return non_blank(value, str(info.field_name))

    @field_validator("evidence_id", "response_to_id")
    @classmethod
    def validate_optional_reference(cls, value: str | None, info: Any) -> str | None:
        """任意の参照IDを空白なしの値へ正規化する."""
        return optional_non_blank(value, str(info.field_name))


class AgentVoteRound(_LlmModel):
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


class ModelMessage(_LlmModel):
    """Provider-independent chat message."""

    role: Literal["system", "human", "ai"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Return a non-empty chat message."""
        return non_blank(value, "model message content")


class DecisionTask(_LlmModel):
    """Authorized inputs for one automated-player decision."""

    day: int = Field(default=1, ge=1)
    player_id: str
    observation: AgentObservation
    deliberation_level: DeliberationLevel = DeliberationLevel.STANDARD
    output_token_limit: int = Field(ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    context: dict[str, object]
    context_checksum: str


class ModelRequest(_LlmModel):
    """One provider-independent model invocation."""

    task: DecisionTask
    messages: tuple[ModelMessage, ...]
    response_schema: dict[str, object]
    prompt_checksum: str


class ModelResponse(_LlmModel):
    """Normalized response returned by every decision-model adapter."""

    content: str
    provider: str
    model: str
    finish_reason: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentModelDecision(_LlmModel):
    """Untrusted decision payload returned by a model."""

    type: AgentActionType
    ability_id: str | None = None
    target_id: str | None = None
    utterance: str | None = None
    topic_id: str | None = None
    position: AgentDiscussionPosition | None = None
    relation: AgentDiscussionRelation | None = None
    evidence_id: str | None = None
    response_to_id: str | None = None
    reason: str = ""

    @field_validator(
        "ability_id", "target_id", "utterance", "topic_id", "evidence_id", "response_to_id"
    )
    @classmethod
    def validate_optional_text(cls, value: str | None, info: Any) -> str | None:
        """Return normalized optional output text."""
        return optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Ensure fields match the selected action shape."""
        if self.type is AgentActionType.SPEECH:
            if self.utterance is None:
                raise ValueError(MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE)
            if self.topic_id is None or self.position is None or self.relation is None:
                raise ValueError("speech requires topic_id, position, and relation")
            if self.target_id is not None:
                raise ValueError(MESSAGE_SPEECH_DECISION_FORBIDS_TARGET)
            return self
        if (
            self.position is not None
            or self.relation is not None
            or self.topic_id is not None
            or self.response_to_id is not None
        ):
            raise ValueError("speech fields are allowed only for speech")
        if (self.type is AgentActionType.USE_ABILITY) != (self.ability_id is not None):
            raise ValueError("use_abilityだけがability_idを持ちます")
        if self.type in AgentDecision.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(message_target_required(self.type.value, "model decisions"))
            if self.utterance is not None:
                raise ValueError(message_message_not_allowed(self.type.value, "model decisions"))
            if self.type is not AgentActionType.VOTE and self.reason:
                raise ValueError("only vote decisions may include reason")
            return self
        if self.type is AgentActionType.PASS:
            if (
                self.target_id is not None
                or self.utterance is not None
                or self.evidence_id is not None
            ):
                raise ValueError(MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD)
            return self
        raise ValueError(message_unsupported_type(self.type.value, "model decision"))


class AgentScenario(_LlmModel):
    """Public scenario premise visible to an agent decision provider."""

    name: str
    premise: str

    @field_validator("name", "premise")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return normalized scenario text."""
        return non_blank(value, str(info.field_name))


class AgentProcedureContext(_LlmModel):
    """Providerへ渡す現在の手続き段階."""

    procedure_id: str
    stage_id: str
    cycle: int = Field(ge=1)
    submission_mode: str

    @field_validator("procedure_id", "stage_id", "submission_mode")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """空でない手続き識別子を返す."""
        return non_blank(value, str(info.field_name))


class AgentAbilityContext(_LlmModel):
    """One ability and its remaining limited uses visible to its owner."""

    id: str
    name: str
    kind: str
    remaining_uses: int | None = Field(default=None, ge=0)


class AgentGameContext(_LlmModel):
    """Authorized, normalized setup facts used for one agent decision."""

    theme_id: str
    theme_name: str
    premise: str
    role_id: str
    role_name: str
    identity_faction: str
    identity_faction_name: str
    victory_team: str
    victory_team_name: str
    objective: str
    abilities: tuple[AgentAbilityContext, ...] = ()
    relevant_rules: dict[str, object] = Field(default_factory=dict)
    action_names: dict[str, str] = Field(default_factory=dict)
    phase_names: dict[str, str] = Field(default_factory=dict)
    setup_checksum: str
    mechanics_checksum: str


class AgentEvidence(_LlmModel):
    """Providerへ渡す型付き公開事実の候補."""

    id: str
    kind: Literal["discussion", "discussion_pass"]
    actor_id: str
    topic_id: str
    position: AgentDiscussionPosition | None = None

    @field_validator("id", "actor_id", "topic_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """空でない公開識別子を返す."""
        return non_blank(value, str(info.field_name))


class AgentObservation(_LlmModel):
    """Provider-independent observation for one player decision."""

    phase: AgentPhase
    day: int
    decision_seed: int = 0
    me: VisiblePlayer
    role: str | None = None
    profile: PlayerProfile | None = None
    scenario: AgentScenario | None = None
    procedure: AgentProcedureContext | None = None
    game_context: AgentGameContext | None = None
    players: list[VisiblePlayer]
    known_roles: dict[str, str] = Field(default_factory=dict)
    known_factions: dict[str, str] = Field(default_factory=dict)
    available_actions: list[AgentAvailableAction] = Field(default_factory=list)
    legal_targets: dict[str, list[str]] = Field(default_factory=dict)
    legal_topics: dict[str, list[str]] = Field(default_factory=dict)
    evidence_options: dict[str, list[AgentEvidence]] = Field(default_factory=dict)
    legal_references: dict[str, list[str]] = Field(default_factory=dict)
    legal_relations: dict[str, list[AgentDiscussionRelation]] = Field(default_factory=dict)
    decision_constraints: dict[str, int] = Field(default_factory=dict)
    speeches: list[AgentSpeech] = Field(default_factory=list)
    vote_rounds: list[AgentVoteRound] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_optional_role(cls, value: str | None) -> str | None:
        """Return a trimmed optional role id."""
        return optional_non_blank(value, "role")

    @field_validator("known_roles", "known_factions")
    @classmethod
    def validate_known_roles(cls, value: dict[str, str]) -> dict[str, str]:
        """Return known role ids keyed by player id."""
        return {
            non_blank(str(player_id), "known role player id"): non_blank(role, "known role")
            for player_id, role in value.items()
        }

    @field_validator("legal_targets", "legal_topics", "legal_references")
    @classmethod
    def validate_legal_targets(
        cls,
        value: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        """Return legal target ids keyed by action type."""
        return {
            non_blank(str(action_key), "action key"): [
                non_blank(str(player_id), "legal target player id") for player_id in player_ids
            ]
            for action_key, player_ids in value.items()
        }

    @field_validator("legal_relations")
    @classmethod
    def validate_legal_relations(
        cls,
        value: dict[str, list[AgentDiscussionRelation]],
    ) -> dict[str, list[AgentDiscussionRelation]]:
        """Return authorized discussion relations keyed by action type."""
        return {
            non_blank(str(action_key), "action key"): [
                AgentDiscussionRelation(item) for item in relations
            ]
            for action_key, relations in value.items()
        }

    @field_validator("decision_constraints")
    @classmethod
    def validate_decision_constraints(cls, value: dict[str, int]) -> dict[str, int]:
        """Return positive effective constraints independent of optional metadata."""
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item < 1
            for item in value.values()
        ):
            raise ValueError("decision constraints must be positive integers")
        return value


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
            raise ValueError(MESSAGE_AGENT_PROFILES_REQUIRED)
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
    ability_id: str | None = None
    target_id: str | None = None
    utterance: str | None = None
    topic_id: str | None = None
    position: AgentDiscussionPosition | None = None
    relation: AgentDiscussionRelation | None = None
    evidence_id: str | None = None
    response_to_id: str | None = None
    reason: str = ""

    TARGET_TYPES: ClassVar[frozenset[AgentActionType]] = frozenset(
        {AgentActionType.VOTE, AgentActionType.USE_ABILITY}
    )

    @field_validator("player_id")
    @classmethod
    def validate_player_id(cls, value: str) -> str:
        """Return a trimmed non-empty player id."""
        return non_blank(value, "player_id")

    @field_validator(
        "ability_id", "target_id", "utterance", "topic_id", "evidence_id", "response_to_id"
    )
    @classmethod
    def validate_optional_text(cls, value: str | None, info: Any) -> str | None:
        """Return a trimmed optional string."""
        return optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Ensure the decision payload matches the decision type."""
        if self.type is AgentActionType.SPEECH:
            if self.utterance is None:
                raise ValueError(MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE)
            if self.target_id is not None:
                raise ValueError(MESSAGE_SPEECH_DECISION_FORBIDS_TARGET)
            if self.topic_id is None or self.position is None or self.relation is None:
                raise ValueError("speech requires topic_id, position, and relation")
            return self

        if (
            self.position is not None
            or self.relation is not None
            or self.topic_id is not None
            or self.response_to_id is not None
        ):
            raise ValueError("speech fields are allowed only for speech decisions")

        if (self.type is AgentActionType.USE_ABILITY) != (self.ability_id is not None):
            raise ValueError("use_abilityだけがability_idを持ちます")

        if self.type in self.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(message_target_required(self.type.value, "decisions"))
            if self.utterance is not None:
                raise ValueError(message_message_not_allowed(self.type.value, "decisions"))
            return self

        if self.type is AgentActionType.PASS:
            if (
                self.target_id is not None
                or self.utterance is not None
                or self.evidence_id is not None
            ):
                raise ValueError(MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD)
            return self

        raise ValueError(message_unsupported_type(self.type.value, "decision"))

    @classmethod
    def speech(
        cls,
        player_id: str,
        utterance: str,
        *,
        topic_id: str,
        position: AgentDiscussionPosition,
        relation: AgentDiscussionRelation,
        evidence_id: str | None = None,
        response_to_id: str | None = None,
    ) -> Self:
        """Create a speech decision."""
        return cls(
            type=AgentActionType.SPEECH,
            player_id=player_id,
            utterance=utterance,
            topic_id=topic_id,
            position=position,
            relation=relation,
            evidence_id=evidence_id,
            response_to_id=response_to_id,
        )

    @classmethod
    def vote(
        cls,
        player_id: str,
        target_id: str,
        *,
        reason: str = "",
        evidence_id: str | None = None,
    ) -> Self:
        """Create a vote decision."""
        return cls(
            type=AgentActionType.VOTE,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
            evidence_id=evidence_id,
        )

    @classmethod
    def use_ability(
        cls, player_id: str, ability_id: str, target_id: str, *, reason: str = ""
    ) -> Self:
        """Create an ability decision."""
        return cls(
            type=AgentActionType.USE_ABILITY,
            player_id=player_id,
            ability_id=ability_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def pass_(cls, player_id: str, *, reason: str = "") -> Self:
        """Create a structured no-op decision."""
        return cls(type=AgentActionType.PASS, player_id=player_id, reason=reason)


__all__ = [
    "AgentAbilityContext",
    "AgentActionType",
    "AgentAvailableAction",
    "AgentDecision",
    "AgentDiscussionPosition",
    "AgentDiscussionRelation",
    "AgentEvidence",
    "AgentGameContext",
    "AgentModelDecision",
    "AgentObservation",
    "AgentPhase",
    "AgentPlayerStatus",
    "AgentProcedureContext",
    "AgentScenario",
    "AgentSpeech",
    "DecisionTask",
    "DeliberationLevel",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "PlayerProfile",
    "PlayerProfileCatalog",
    "VisiblePlayer",
]
