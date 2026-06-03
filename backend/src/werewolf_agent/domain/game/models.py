"""Public domain models for the deterministic headless game."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import Field, field_validator, model_validator

from werewolf_agent.commons.shared.definitions import LocalRulesDefinition
from werewolf_agent.commons.shared.messages import (
    MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD,
    MESSAGE_PLAYER_COUNT_AT_LEAST_ONE,
    MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE,
    MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT,
    MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE,
    MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF,
    MESSAGE_ROLES_REQUIRED,
    MESSAGE_SPEECH_ACTION_FORBIDS_TARGET,
    MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE,
    message_message_not_allowed,
    message_role_count_must_be_zero_or_greater,
    message_target_required,
    message_unknown_role_in_role_counts,
    message_unsupported_abilities,
    message_unsupported_faction,
    message_unsupported_type,
)
from werewolf_agent.commons.shared.models import StrictModel
from werewolf_agent.commons.shared.validation import non_blank, optional_non_blank

FACTION_VILLAGE = "village"
FACTION_WEREWOLF = "werewolf"

ABILITY_NIGHT_ATTACK = "night_attack"
ABILITY_PACK_KNOWLEDGE = "pack_knowledge"
ABILITY_INSPECT = "inspect"
ABILITY_GUARD = "guard"

SUPPORTED_FACTIONS = frozenset({FACTION_VILLAGE, FACTION_WEREWOLF})
SUPPORTED_ABILITIES = frozenset(
    {
        ABILITY_NIGHT_ATTACK,
        ABILITY_PACK_KNOWLEDGE,
        ABILITY_INSPECT,
        ABILITY_GUARD,
    }
)


class Phase(StrEnum):
    """High-level game phases."""

    SETUP = "setup"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    FINISHED = "finished"


class PlayerStatus(StrEnum):
    """Current player life state."""

    ALIVE = "alive"
    DEAD = "dead"


class ActionType(StrEnum):
    """Structured actions accepted by the headless game."""

    SPEECH = "speech"
    VOTE = "vote"
    WEREWOLF_ATTACK = "werewolf_attack"
    SEER_INSPECT = "seer_inspect"
    KNIGHT_GUARD = "knight_guard"
    PASS = "pass"


class EventVisibility(StrEnum):
    """Intended visibility for domain events emitted by the headless core."""

    PUBLIC = "public"
    PLAYER_PRIVATE = "player_private"
    DEBUG = "debug"


class _DomainModel(StrictModel):
    """Base model for game domain values."""


class _PlayerBase(_DomainModel):
    """Shared identity fields for players in setup, state, and observations."""

    id: str
    name: str

    @field_validator("id", "name")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return non_blank(value, str(info.field_name))


class Player(_PlayerBase):
    """Player data used by setup, full snapshots, and observations."""

    role: str | None = None
    status: PlayerStatus = PlayerStatus.ALIVE
    eliminated_day: int | None = None
    killed_night: int | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        """Return a normalized role id when assigned."""
        return optional_non_blank(value, "role")

    @property
    def is_alive(self) -> bool:
        """Return whether the player can act."""
        return self.status is PlayerStatus.ALIVE


class LocalRules(LocalRulesDefinition):
    """Resolved local rule flags used by the game core."""


class RoleDefinition(_DomainModel):
    """Game-only role definition resolved from the role catalog."""

    faction: str
    abilities: tuple[str, ...] = ()

    @field_validator("faction")
    @classmethod
    def validate_faction(cls, value: str) -> str:
        """Return a supported faction id."""
        faction = non_blank(value, "faction")
        if faction not in SUPPORTED_FACTIONS:
            raise ValueError(message_unsupported_faction(faction))
        return faction

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return supported ability ids without duplicates."""
        abilities = tuple(non_blank(item, "ability") for item in value)
        if len(set(abilities)) != len(abilities):
            raise ValueError(MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE)
        unknown = sorted(set(abilities) - SUPPORTED_ABILITIES)
        if unknown:
            raise ValueError(message_unsupported_abilities(unknown))
        return abilities

    def has_ability(self, ability: str) -> bool:
        """Return whether the role has the requested game ability."""
        return ability in self.abilities


class RoleCatalog(_DomainModel):
    """Game-only role catalog resolved from role definitions."""

    roles: dict[str, RoleDefinition]

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: dict[str, RoleDefinition]) -> dict[str, RoleDefinition]:
        """Return role definitions keyed by normalized role id."""
        roles = {
            non_blank(str(role_id), "role id"): definition for role_id, definition in value.items()
        }
        if not roles:
            raise ValueError(MESSAGE_ROLES_REQUIRED)
        return roles

    def require_role(self, role: str) -> RoleDefinition:
        """Return a role definition or raise ``KeyError`` for unknown roles."""
        return self.roles[role]

    def faction_for_role(self, role: str) -> str:
        """Return the configured faction for one role."""
        return self.require_role(role).faction

    def role_has_ability(self, role: str | None, ability: str) -> bool:
        """Return whether a role has one configured game ability."""
        if role is None:
            return False
        return self.require_role(role).has_ability(ability)


class GameConfig(_DomainModel):
    """Settings for one deterministic game."""

    player_count: int
    role_counts: dict[str, int]
    rules: LocalRules
    roles: RoleCatalog

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        """Validate role-count invariants for one game state."""
        if self.player_count < 1:
            raise ValueError(MESSAGE_PLAYER_COUNT_AT_LEAST_ONE)

        role_total = 0
        for role, count in self.role_counts.items():
            role_id = non_blank(str(role), "role_counts key")
            if role_id not in self.roles.roles:
                raise ValueError(message_unknown_role_in_role_counts(role_id))
            if count < 0:
                raise ValueError(message_role_count_must_be_zero_or_greater(role_id))
            role_total += count
        if role_total != self.player_count:
            raise ValueError(MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT)
        werewolf_side_count = sum(
            count
            for role, count in self.role_counts.items()
            if self.roles.faction_for_role(role) == FACTION_WEREWOLF
        )
        if werewolf_side_count < 1:
            raise ValueError(MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF)
        village_side_count = sum(
            count
            for role, count in self.role_counts.items()
            if self.roles.faction_for_role(role) == FACTION_VILLAGE
        )
        if village_side_count < 1:
            raise ValueError(MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE)
        return self


class _ActionBase(_DomainModel):
    """Shared fields for every structured player action."""

    type: ActionType
    player_id: str
    reason: str = ""

    @field_validator("player_id")
    @classmethod
    def validate_player_id(cls, value: str) -> str:
        """Return a trimmed non-empty player id."""
        return non_blank(value, "player_id")


class Action(_ActionBase):
    """One structured action submitted by an agent or player."""

    target_id: str | None = None
    message: str | None = None

    TARGET_TYPES: ClassVar[frozenset[ActionType]] = frozenset(
        {
            ActionType.VOTE,
            ActionType.WEREWOLF_ATTACK,
            ActionType.SEER_INSPECT,
            ActionType.KNIGHT_GUARD,
        }
    )
    NIGHT_TYPES: ClassVar[frozenset[ActionType]] = frozenset(
        {
            ActionType.WEREWOLF_ATTACK,
            ActionType.SEER_INSPECT,
            ActionType.KNIGHT_GUARD,
        }
    )

    @field_validator("target_id", "message")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: Any) -> str | None:
        """Return a trimmed optional string."""
        return optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Ensure the action payload matches the action type."""
        if self.type is ActionType.SPEECH:
            if self.message is None:
                raise ValueError(MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE)
            if self.target_id is not None:
                raise ValueError(MESSAGE_SPEECH_ACTION_FORBIDS_TARGET)
            return self

        if self.type in self.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(message_target_required(self.type.value, "actions"))
            if self.message is not None:
                raise ValueError(message_message_not_allowed(self.type.value, "actions"))
            return self

        if self.type is ActionType.PASS:
            if self.target_id is not None or self.message is not None:
                raise ValueError(MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD)
            return self

        raise ValueError(message_unsupported_type(self.type.value, "action"))

    @property
    def is_night_action(self) -> bool:
        """Return whether this action is resolved during the night phase."""
        return self.type in self.NIGHT_TYPES

    @classmethod
    def speech(cls, player_id: str, message: str) -> Self:
        """Create a day-discussion speech action."""
        return cls(type=ActionType.SPEECH, player_id=player_id, message=message)

    @classmethod
    def vote(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a voting action."""
        return cls(
            type=ActionType.VOTE,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def attack(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a werewolf attack action."""
        return cls(
            type=ActionType.WEREWOLF_ATTACK,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def inspect(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a seer inspection action."""
        return cls(
            type=ActionType.SEER_INSPECT,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def guard(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a knight guard action."""
        return cls(
            type=ActionType.KNIGHT_GUARD,
            player_id=player_id,
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def pass_(cls, player_id: str, *, reason: str = "") -> Self:
        """Create a structured no-op action."""
        return cls(type=ActionType.PASS, player_id=player_id, reason=reason)


class _RoundResult(_DomainModel):
    """Shared field for phase resolution records."""

    day: int


class VoteResult(_RoundResult):
    """Resolved vote outcome for one day."""

    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: str


class InspectionResult(_RoundResult):
    """Private seer result generated by a resolved night phase."""

    seer_id: str
    target_id: str
    target_role: str
    target_faction: str


class NightResult(_RoundResult):
    """Resolved night outcome."""

    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[InspectionResult] = Field(default_factory=list)


class SpeechRecord(_RoundResult):
    """One accepted public day-discussion speech."""

    player_id: str
    message: str
    reason: str = ""

    @field_validator("player_id", "message")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return non_blank(value, str(info.field_name))

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Return a trimmed optional reason string."""
        return value.strip()


class WinResult(_DomainModel):
    """Resolved game winner."""

    winner: str
    reason: str
    day: int
    winning_player_ids: list[str]


class GameHistory(_DomainModel):
    """Append-only records produced by game phases."""

    speeches: list[SpeechRecord] = Field(default_factory=list)
    votes: list[VoteResult] = Field(default_factory=list)
    nights: list[NightResult] = Field(default_factory=list)


class GameSnapshot(_DomainModel):
    """Serializable full game state for application boundaries."""

    config: GameConfig
    phase: Phase
    day: int
    players: dict[str, Player]
    history: GameHistory = Field(default_factory=GameHistory)
    win_result: WinResult | None = None


class PendingActions(_DomainModel):
    """Actions collected for phases that resolve in batches."""

    votes: dict[str, Action] = Field(default_factory=dict)
    night_actions: dict[str, Action] = Field(default_factory=dict)


class Observation(_DomainModel):
    """Information visible to one player-agent at one point in time."""

    phase: Phase
    day: int
    me: Player
    players: list[Player]
    known_roles: dict[str, str] = Field(default_factory=dict)
    available_actions: list[ActionType] = Field(default_factory=list)
    history: GameHistory = Field(default_factory=GameHistory)
    win_result: WinResult | None = None


class DomainEvent(_DomainModel):
    """Headless domain event that an outer layer may log or adapt."""

    event_type: str
    phase: Phase | None = None
    day: int | None = None
    actor_id: str | None = None
    visibility: EventVisibility = EventVisibility.PUBLIC
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return non_blank(value, str(info.field_name))


__all__ = [
    "ABILITY_GUARD",
    "ABILITY_INSPECT",
    "ABILITY_NIGHT_ATTACK",
    "ABILITY_PACK_KNOWLEDGE",
    "FACTION_VILLAGE",
    "FACTION_WEREWOLF",
    "SUPPORTED_ABILITIES",
    "SUPPORTED_FACTIONS",
    "Action",
    "ActionType",
    "DomainEvent",
    "EventVisibility",
    "GameConfig",
    "GameHistory",
    "GameSnapshot",
    "InspectionResult",
    "LocalRules",
    "NightResult",
    "Observation",
    "PendingActions",
    "Phase",
    "Player",
    "PlayerStatus",
    "RoleCatalog",
    "RoleDefinition",
    "SpeechRecord",
    "VoteResult",
    "WinResult",
]
