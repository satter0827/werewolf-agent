"""Public domain models for the deterministic headless game."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Role(StrEnum):
    """Playable roles supported by the MVP rules."""

    VILLAGER = "villager"
    WEREWOLF = "werewolf"
    SEER = "seer"
    KNIGHT = "knight"


class Faction(StrEnum):
    """Win-condition factions."""

    VILLAGE = "village"
    WEREWOLF = "werewolf"


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


class TieBreakPolicy(StrEnum):
    """How vote ties are resolved."""

    NO_ELIMINATION = "no_elimination"
    RANDOM_ELIMINATION = "random_elimination"


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


class _DomainModel(BaseModel):
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


class _PlayerBase(_DomainModel):
    """Shared identity fields for players in setup, state, and observations."""

    id: str
    name: str

    @field_validator("id", "name")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class Player(_PlayerBase):
    """Player data used by setup, full snapshots, and observations."""

    role: Role | None = None
    status: PlayerStatus = PlayerStatus.ALIVE
    eliminated_day: int | None = None
    killed_night: int | None = None

    @property
    def is_alive(self) -> bool:
        """Return whether the player can act."""
        return self.status is PlayerStatus.ALIVE


class GameConfig(_DomainModel):
    """Settings for one deterministic game run."""

    game_id: str = "game"
    player_count: int
    role_counts: dict[Role, int]
    seed: int | None = None
    day_speech_turns: int = 1
    tie_break_policy: TieBreakPolicy = TieBreakPolicy.NO_ELIMINATION
    allow_self_vote: bool = False

    @field_validator("game_id")
    @classmethod
    def validate_game_id(cls, value: str) -> str:
        """Return a trimmed non-empty game id."""
        return _non_blank(value, "game_id")

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        """Validate role-count invariants for one game state."""
        if self.player_count < 1:
            msg = "player_count must be at least 1"
            raise ValueError(msg)
        if self.day_speech_turns < 1:
            msg = "day_speech_turns must be at least 1"
            raise ValueError(msg)

        role_total = 0
        for role, count in self.role_counts.items():
            if count < 0:
                msg = f"role_counts[{role.value}] must be zero or greater"
                raise ValueError(msg)
            role_total += count
        if role_total != self.player_count:
            msg = "role_counts must sum to player_count"
            raise ValueError(msg)
        if self.role_counts.get(Role.WEREWOLF, 0) < 1:
            msg = "role_counts must include at least one werewolf"
            raise ValueError(msg)
        if role_total - self.role_counts.get(Role.WEREWOLF, 0) < 1:
            msg = "role_counts must include at least one village-side player"
            raise ValueError(msg)
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
        return _non_blank(value, "player_id")


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
        return _optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Ensure the action payload matches the action type."""
        if self.type is ActionType.SPEECH:
            if self.message is None:
                raise ValueError("message is required for speech actions")
            if self.target_id is not None:
                raise ValueError("target_id is not allowed for speech actions")
            return self

        if self.type in self.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(f"target_id is required for {self.type.value} actions")
            if self.message is not None:
                raise ValueError(f"message is not allowed for {self.type.value} actions")
            return self

        if self.type is ActionType.PASS:
            if self.target_id is not None or self.message is not None:
                raise ValueError("pass actions cannot include target_id or message")
            return self

        raise ValueError(f"unsupported action type: {self.type.value}")

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
    tie_break_policy: TieBreakPolicy


class InspectionResult(_RoundResult):
    """Private seer result generated by a resolved night phase."""

    seer_id: str
    target_id: str
    target_role: Role
    target_faction: Faction


class NightResult(_RoundResult):
    """Resolved night outcome."""

    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[InspectionResult] = Field(default_factory=list)


class WinResult(_DomainModel):
    """Resolved game winner."""

    winner: Faction
    reason: str
    day: int
    winning_player_ids: list[str]


class GameHistory(_DomainModel):
    """Append-only records produced by game phases."""

    speeches: list[Action] = Field(default_factory=list)
    votes: list[VoteResult] = Field(default_factory=list)
    nights: list[NightResult] = Field(default_factory=list)


class GameSnapshot(_DomainModel):
    """Serializable full game state for application boundaries."""

    game_id: str
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
    known_roles: dict[str, Role] = Field(default_factory=dict)
    available_actions: list[ActionType] = Field(default_factory=list)
    history: GameHistory = Field(default_factory=GameHistory)
    win_result: WinResult | None = None


class DomainEvent(_DomainModel):
    """Headless domain event that an outer layer may log or adapt."""

    event_type: str
    game_id: str
    phase: Phase | None = None
    day: int | None = None
    actor_id: str | None = None
    visibility: EventVisibility = EventVisibility.PUBLIC
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type", "game_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


__all__ = [
    "Action",
    "ActionType",
    "DomainEvent",
    "EventVisibility",
    "Faction",
    "GameConfig",
    "GameHistory",
    "GameSnapshot",
    "InspectionResult",
    "NightResult",
    "Observation",
    "PendingActions",
    "Phase",
    "Player",
    "PlayerStatus",
    "Role",
    "TieBreakPolicy",
    "VoteResult",
    "WinResult",
]
