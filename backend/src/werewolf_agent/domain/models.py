"""Public domain models and the headless game facade."""

from __future__ import annotations

import random
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Literal, Protocol, Self, TypeAlias

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


class PlayerConfig(_DomainModel):
    """Initial player definition supplied by an outer interface."""

    player_id: str
    name: str
    role: Role | None = None

    @field_validator("player_id", "name")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class GameConfig(_DomainModel):
    """Settings for one deterministic game run."""

    game_id: str = "game"
    player_count: int = 6
    role_counts: dict[Role, int] = Field(
        default_factory=lambda: {
            Role.WEREWOLF: 1,
            Role.SEER: 1,
            Role.KNIGHT: 1,
            Role.VILLAGER: 3,
        }
    )
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
        """Validate MVP player and role-count constraints."""
        if self.player_count < 5 or self.player_count > 8:
            msg = "player_count must be between 5 and 8"
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


class PlayerState(_DomainModel):
    """Full internal player state exposed only through snapshots."""

    player_id: str
    name: str
    role: Role
    status: PlayerStatus = PlayerStatus.ALIVE
    eliminated_day: int | None = None
    killed_night: int | None = None


class ObservedPlayer(_DomainModel):
    """Player information visible to one observer."""

    player_id: str
    name: str
    status: PlayerStatus
    role: Role | None = None


class SpeechAction(_DomainModel):
    """A public day-discussion message from one player."""

    action_type: Literal["speech"] = "speech"
    player_id: str
    message: str

    @field_validator("player_id", "message")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class VoteAction(_DomainModel):
    """A vote cast during the voting phase."""

    action_type: Literal["vote"] = "vote"
    player_id: str
    target_id: str
    reason: str = ""

    @field_validator("player_id", "target_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class WerewolfAttackAction(_DomainModel):
    """A werewolf attack target submitted during night."""

    action_type: Literal["werewolf_attack"] = "werewolf_attack"
    player_id: str
    target_id: str
    reason: str = ""

    @field_validator("player_id", "target_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class SeerInspectAction(_DomainModel):
    """A seer inspection target submitted during night."""

    action_type: Literal["seer_inspect"] = "seer_inspect"
    player_id: str
    target_id: str
    reason: str = ""

    @field_validator("player_id", "target_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class KnightGuardAction(_DomainModel):
    """A knight guard target submitted during night."""

    action_type: Literal["knight_guard"] = "knight_guard"
    player_id: str
    target_id: str
    reason: str = ""

    @field_validator("player_id", "target_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: Any) -> str:
        """Return a trimmed non-empty string."""
        return _non_blank(value, str(info.field_name))


class PassAction(_DomainModel):
    """A structured no-op for agents that have no valid action."""

    action_type: Literal["pass"] = "pass"
    player_id: str
    reason: str = ""

    @field_validator("player_id")
    @classmethod
    def validate_player_id(cls, value: str) -> str:
        """Return a trimmed non-empty player id."""
        return _non_blank(value, "player_id")


NightAction: TypeAlias = WerewolfAttackAction | SeerInspectAction | KnightGuardAction
AgentAction: TypeAlias = SpeechAction | VoteAction | NightAction | PassAction


class VoteResult(_DomainModel):
    """Resolved vote outcome for one day."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: TieBreakPolicy


class SeerInspectionResult(_DomainModel):
    """Private seer result generated by a resolved night phase."""

    day: int
    seer_id: str
    target_id: str
    target_role: Role
    target_faction: Faction


class NightResult(_DomainModel):
    """Resolved night outcome."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[SeerInspectionResult] = Field(default_factory=list)


class WinResult(_DomainModel):
    """Resolved game winner."""

    winner: Faction
    reason: str
    day: int
    winning_player_ids: list[str]


class GameSnapshot(_DomainModel):
    """Serializable full game state for application boundaries."""

    game_id: str
    config: GameConfig
    phase: Phase
    day: int
    players: dict[str, PlayerState]
    speeches: list[SpeechAction] = Field(default_factory=list)
    vote_history: list[VoteResult] = Field(default_factory=list)
    night_history: list[NightResult] = Field(default_factory=list)
    win_result: WinResult | None = None


class Observation(_DomainModel):
    """Information visible to one player-agent at one point in time."""

    player_id: str
    phase: Phase
    day: int
    self_player: ObservedPlayer
    players: list[ObservedPlayer]
    known_roles: dict[str, Role] = Field(default_factory=dict)
    available_actions: list[str] = Field(default_factory=list)
    speeches: list[SpeechAction] = Field(default_factory=list)
    vote_history: list[VoteResult] = Field(default_factory=list)
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


class DomainEventSink(Protocol):
    """Destination for domain events emitted by the headless game core."""

    def write(self, event: DomainEvent) -> None:
        """Write one domain event."""


class Game:
    """Headless game facade; detailed rules live behind domain services."""

    def __init__(
        self,
        snapshot: GameSnapshot,
        *,
        rng: random.Random | None = None,
        event_sink: DomainEventSink | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._rng = rng or random.Random(snapshot.config.seed)
        self._event_sink = event_sink
        self._pending_votes: dict[str, VoteAction] = {}
        self._pending_night_actions: dict[str, NightAction] = {}

    @classmethod
    def start(
        cls,
        *,
        config: GameConfig,
        players: Sequence[PlayerConfig],
        rng: random.Random | None = None,
        event_sink: DomainEventSink | None = None,
    ) -> Self:
        """Create a new game from injected settings, players, and runtime services."""
        from werewolf_agent.domain.service import create_game_snapshot

        runtime_rng = rng or random.Random(config.seed)
        snapshot = create_game_snapshot(config, players, runtime_rng)
        game = cls(snapshot, rng=runtime_rng, event_sink=event_sink)
        game._emit(
            DomainEvent(
                event_type="game_started",
                game_id=snapshot.game_id,
                phase=snapshot.phase,
                day=snapshot.day,
                payload={
                    "player_count": config.player_count,
                    "role_counts": {
                        role.value: count for role, count in config.role_counts.items()
                    },
                },
            )
        )
        return game

    @classmethod
    def restore(
        cls,
        snapshot: GameSnapshot,
        *,
        rng: random.Random | None = None,
        event_sink: DomainEventSink | None = None,
    ) -> Self:
        """Restore a headless game facade from a previously persisted snapshot."""
        return cls(snapshot, rng=rng, event_sink=event_sink)

    @property
    def phase(self) -> Phase:
        """Return the current phase."""
        return self._snapshot.phase

    @property
    def day(self) -> int:
        """Return the current day."""
        return self._snapshot.day

    def snapshot(self) -> GameSnapshot:
        """Return a defensive copy of the current full game state."""
        return self._snapshot.model_copy(deep=True)

    def observation_for(self, player_id: str) -> Observation:
        """Return the information visible to one player."""
        from werewolf_agent.domain.service import build_player_observation

        return build_player_observation(self._snapshot, player_id)

    def submit_day_action(self, action: SpeechAction) -> SpeechAction:
        """Record one day-discussion action."""
        from werewolf_agent.domain.service import record_day_speech

        self._snapshot, events = record_day_speech(self._snapshot, action)
        self._emit_all(events)
        return action

    def submit_vote(self, action: VoteAction) -> VoteAction:
        """Record one vote for the current voting phase."""
        from werewolf_agent.domain.service import record_vote

        self._pending_votes = record_vote(
            self._snapshot,
            self._snapshot.config,
            self._pending_votes,
            action,
        )
        self._emit(
            DomainEvent(
                event_type="vote_submitted",
                game_id=self._snapshot.game_id,
                phase=self._snapshot.phase,
                day=self._snapshot.day,
                actor_id=action.player_id,
                payload={"target_id": action.target_id},
            )
        )
        return action

    def submit_night_action(self, action: NightAction) -> NightAction:
        """Record one night action for later resolution."""
        from werewolf_agent.domain.service import record_night_action

        self._pending_night_actions = record_night_action(
            self._snapshot,
            self._pending_night_actions,
            action,
        )
        self._emit(
            DomainEvent(
                event_type="night_action_submitted",
                game_id=self._snapshot.game_id,
                phase=self._snapshot.phase,
                day=self._snapshot.day,
                actor_id=action.player_id,
                visibility=EventVisibility.PLAYER_PRIVATE,
                payload={"action_type": action.action_type},
            )
        )
        return action

    def advance_phase(self) -> GameSnapshot:
        """Advance the deterministic state machine by one phase."""
        from werewolf_agent.domain.service import advance_game_phase

        snapshot, events, clear_votes, clear_night_actions = advance_game_phase(
            self._snapshot,
            self._snapshot.config,
            self._pending_votes,
            self._pending_night_actions,
            self._rng,
        )
        self._snapshot = snapshot
        if clear_votes:
            self._pending_votes = {}
        if clear_night_actions:
            self._pending_night_actions = {}
        self._emit_all(events)
        return self.snapshot()

    def _emit(self, event: DomainEvent) -> None:
        if self._event_sink is not None:
            self._event_sink.write(event)

    def _emit_all(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            self._emit(event)


__all__ = [
    "AgentAction",
    "DomainEvent",
    "DomainEventSink",
    "EventVisibility",
    "Faction",
    "Game",
    "GameConfig",
    "GameSnapshot",
    "KnightGuardAction",
    "NightAction",
    "NightResult",
    "Observation",
    "ObservedPlayer",
    "PassAction",
    "Phase",
    "PlayerConfig",
    "PlayerState",
    "PlayerStatus",
    "Role",
    "SeerInspectAction",
    "SeerInspectionResult",
    "SpeechAction",
    "TieBreakPolicy",
    "VoteAction",
    "VoteResult",
    "WerewolfAttackAction",
    "WinResult",
]
