"""Immutable values for the deterministic headless game."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Self

from werewolf_agent.domain._messages import (
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
from werewolf_agent.domain._model import freeze_value, frozen_mapping, non_blank, optional_non_blank

FACTION_VILLAGE = "village"
FACTION_WEREWOLF = "werewolf"
ABILITY_NIGHT_ATTACK = "night_attack"
ABILITY_PACK_KNOWLEDGE = "pack_knowledge"
ABILITY_INSPECT = "inspect"
ABILITY_GUARD = "guard"
SUPPORTED_FACTIONS = frozenset({FACTION_VILLAGE, FACTION_WEREWOLF})


class Phase(StrEnum):
    """Game lifecycle phases."""

    SETUP = "setup"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    FINISHED = "finished"


class PlayerStatus(StrEnum):
    """Player survival states."""

    ALIVE = "alive"
    DEAD = "dead"


class ActionType(StrEnum):
    """Actions understood by the standard domain core."""

    SPEECH = "speech"
    VOTE = "vote"
    WEREWOLF_ATTACK = "werewolf_attack"
    SEER_INSPECT = "seer_inspect"
    KNIGHT_GUARD = "knight_guard"
    PASS = "pass"


class EventVisibility(StrEnum):
    """Visibility classes attached to domain events."""

    PUBLIC = "public"
    PLAYER_PRIVATE = "player_private"
    DEBUG = "debug"


@dataclass(frozen=True)
class AbilityDefinition:
    """Immutable configuration for one role ability."""

    phase: Phase
    action: ActionType
    validation_policy: str
    resolution_policy: str
    target_policy: str
    start_day: int

    def __post_init__(self) -> None:
        """Normalize policy IDs and reject unsupported ability combinations."""
        object.__setattr__(self, "phase", Phase(self.phase))
        object.__setattr__(self, "action", ActionType(self.action))
        for name in ("validation_policy", "resolution_policy", "target_policy"):
            object.__setattr__(self, name, non_blank(getattr(self, name), name))
        if self.start_day < 1:
            raise ValueError("start_day must be at least 1.")
        if self.validation_policy != "standard":
            raise ValueError(f"Unknown ability validation policy: {self.validation_policy}")
        if self.resolution_policy != "standard":
            raise ValueError(f"Unknown ability resolution policy: {self.resolution_policy}")
        if self.target_policy not in {"none", "alive", "other_alive", "other_alive_non_pack"}:
            raise ValueError(f"Unknown ability target policy: {self.target_policy}")
        night_actions = {
            ActionType.WEREWOLF_ATTACK,
            ActionType.SEER_INSPECT,
            ActionType.KNIGHT_GUARD,
        }
        if self.action not in night_actions | {ActionType.PASS}:
            raise ValueError(f"Action {self.action.value} is not implemented as a role ability.")
        if self.action in night_actions and self.phase is not Phase.NIGHT:
            raise ValueError(f"Action {self.action.value} is only implemented for the night phase.")
        if self.action in night_actions and self.target_policy == "none":
            raise ValueError(f"Action {self.action.value} requires a target policy.")
        if self.action is ActionType.PASS and self.target_policy != "none":
            raise ValueError("Pass abilities cannot define a target policy.")


@dataclass(frozen=True)
class Player:
    """Immutable player state inside one game."""

    id: str
    name: str
    role: str | None = None
    status: PlayerStatus = PlayerStatus.ALIVE
    eliminated_day: int | None = None
    killed_night: int | None = None

    def __post_init__(self) -> None:
        """Normalize player identifiers and optional role data."""
        object.__setattr__(self, "id", non_blank(self.id, "id"))
        object.__setattr__(self, "name", non_blank(self.name, "name"))
        object.__setattr__(self, "role", optional_non_blank(self.role, "role"))
        object.__setattr__(self, "status", PlayerStatus(self.status))
        for field_name in ("eliminated_day", "killed_night"):
            value = getattr(self, field_name)
            if value is not None and value < 1:
                raise ValueError(f"{field_name} must be at least 1.")
        death_markers = (self.eliminated_day, self.killed_night)
        if self.status is PlayerStatus.ALIVE and any(value is not None for value in death_markers):
            raise ValueError("Alive players cannot have death metadata.")
        if (
            self.status is PlayerStatus.DEAD
            and sum(value is not None for value in death_markers) != 1
        ):
            raise ValueError("Dead players require exactly one death marker.")

    @property
    def is_alive(self) -> bool:
        """Return whether the player can currently act."""
        return self.status is PlayerStatus.ALIVE


@dataclass(frozen=True)
class LocalRules:
    """Configurable values for standard game behavior."""

    day_speech_limit_per_player: int
    allow_self_vote: bool
    allow_vote_revision: bool
    allow_night_action_revision: bool
    enable_first_night_attack: bool
    enable_no_elimination_on_tie: bool
    enable_random_elimination_on_tie: bool
    allow_knight_self_guard: bool
    allow_knight_repeat_guard: bool
    allow_seer_self_inspect: bool
    allow_werewolf_friendly_fire: bool
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool = True

    def __post_init__(self) -> None:
        """Validate mutually dependent local rule values."""
        if not 0 <= self.day_speech_limit_per_player <= 100:
            raise ValueError("day_speech_limit_per_player must be between 0 and 100.")
        if (self.enable_no_elimination_on_tie, self.enable_random_elimination_on_tie).count(
            True
        ) != 1:
            raise ValueError("Exactly one tie-resolution policy must be enabled.")


@dataclass(frozen=True)
class RoleDefinition:
    """Immutable faction and ability membership for one role."""

    faction: str
    abilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize the faction and unique ability IDs."""
        faction = non_blank(self.faction, "faction")
        if faction not in SUPPORTED_FACTIONS:
            raise ValueError(message_unsupported_faction(faction))
        abilities = tuple(non_blank(item, "ability") for item in self.abilities)
        if len(set(abilities)) != len(abilities):
            raise ValueError(MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE)
        object.__setattr__(self, "faction", faction)
        object.__setattr__(self, "abilities", abilities)

    def has_ability(self, ability: str) -> bool:
        """Return whether this role owns an ability ID."""
        return ability in self.abilities


@dataclass(frozen=True)
class RoleCatalog:
    """Immutable lookup of configured role definitions."""

    roles: Mapping[str, RoleDefinition]

    def __post_init__(self) -> None:
        """Normalize role IDs and freeze the catalog."""
        roles = {non_blank(str(role_id), "role id"): value for role_id, value in self.roles.items()}
        if not roles:
            raise ValueError(MESSAGE_ROLES_REQUIRED)
        object.__setattr__(self, "roles", frozen_mapping(roles))

    def require_role(self, role: str) -> RoleDefinition:
        """Return one configured role or raise for an unknown ID."""
        return self.roles[role]

    def faction_for_role(self, role: str) -> str:
        """Return the canonical faction ID for one role."""
        return self.require_role(role).faction

    def role_has_ability(self, role: str | None, ability: str) -> bool:
        """Return whether an assigned role owns an ability."""
        return role is not None and self.require_role(role).has_ability(ability)


@dataclass(frozen=True)
class GameConfig:
    """Validated immutable configuration embedded in game state."""

    player_count: int
    role_counts: Mapping[str, int]
    rules: LocalRules
    roles: RoleCatalog
    abilities: Mapping[str, AbilityDefinition]
    phase_order: tuple[Phase, ...] = (Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.VOTING)

    def __post_init__(self) -> None:
        """Freeze nested values and validate all configuration references."""
        role_counts = {
            non_blank(str(role), "role_counts key"): count
            for role, count in self.role_counts.items()
        }
        abilities = {
            non_blank(str(key), "ability id"): value for key, value in self.abilities.items()
        }
        object.__setattr__(self, "role_counts", frozen_mapping(role_counts))
        object.__setattr__(self, "abilities", frozen_mapping(abilities))
        object.__setattr__(self, "phase_order", tuple(self.phase_order))
        if self.player_count < 1:
            raise ValueError(MESSAGE_PLAYER_COUNT_AT_LEAST_ONE)
        for role, count in role_counts.items():
            if role not in self.roles.roles:
                raise ValueError(message_unknown_role_in_role_counts(role))
            if count < 0:
                raise ValueError(message_role_count_must_be_zero_or_greater(role))
        if sum(role_counts.values()) != self.player_count:
            raise ValueError(MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT)
        if (
            sum(
                count
                for role, count in role_counts.items()
                if self.roles.faction_for_role(role) == FACTION_WEREWOLF
            )
            < 1
        ):
            raise ValueError(MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF)
        if (
            sum(
                count
                for role, count in role_counts.items()
                if self.roles.faction_for_role(role) == FACTION_VILLAGE
            )
            < 1
        ):
            raise ValueError(MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE)
        referenced = {ability for role in self.roles.roles.values() for ability in role.abilities}
        unknown = sorted(referenced - set(abilities))
        if unknown:
            raise ValueError(message_unsupported_abilities(unknown))
        expected = {Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.VOTING}
        if len(self.phase_order) != len(expected) or set(self.phase_order) != expected:
            raise ValueError(
                "phase_order must contain night, day_discussion, and voting exactly once."
            )


@dataclass(frozen=True)
class Action:
    """Validated player intent accepted by the game aggregate."""

    type: ActionType
    player_id: str
    reason: str = ""
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
        {ActionType.WEREWOLF_ATTACK, ActionType.SEER_INSPECT, ActionType.KNIGHT_GUARD}
    )

    def __post_init__(self) -> None:
        """Normalize action fields and enforce payload shape by action type."""
        object.__setattr__(self, "type", ActionType(self.type))
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "target_id", optional_non_blank(self.target_id, "target_id"))
        object.__setattr__(self, "message", optional_non_blank(self.message, "message"))
        if self.type is ActionType.SPEECH:
            if self.message is None:
                raise ValueError(MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE)
            if self.target_id is not None:
                raise ValueError(MESSAGE_SPEECH_ACTION_FORBIDS_TARGET)
        elif self.type in self.TARGET_TYPES:
            if self.target_id is None:
                raise ValueError(message_target_required(self.type.value, "actions"))
            if self.message is not None:
                raise ValueError(message_message_not_allowed(self.type.value, "actions"))
        elif self.type is ActionType.PASS:
            if self.target_id is not None or self.message is not None:
                raise ValueError(MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD)
        else:
            raise ValueError(message_unsupported_type(self.type.value, "action"))

    @property
    def is_night_action(self) -> bool:
        """Return whether this action is resolved during the night phase."""
        return self.type in self.NIGHT_TYPES

    @classmethod
    def speech(cls, player_id: str, message: str) -> Self:
        """Create a public speech action."""
        return cls(ActionType.SPEECH, player_id, message=message)

    @classmethod
    def vote(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a vote action against one living player."""
        return cls(ActionType.VOTE, player_id, reason=reason, target_id=target_id)

    @classmethod
    def attack(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a werewolf night attack action."""
        return cls(ActionType.WEREWOLF_ATTACK, player_id, reason=reason, target_id=target_id)

    @classmethod
    def inspect(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a seer inspection action."""
        return cls(ActionType.SEER_INSPECT, player_id, reason=reason, target_id=target_id)

    @classmethod
    def guard(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a knight guard action."""
        return cls(ActionType.KNIGHT_GUARD, player_id, reason=reason, target_id=target_id)

    @classmethod
    def pass_(cls, player_id: str, *, reason: str = "") -> Self:
        """Create an explicit no-op action."""
        return cls(ActionType.PASS, player_id, reason=reason)


@dataclass(frozen=True)
class VoteResult:
    """Resolved public and private facts for one vote round."""

    day: int
    tie_break_policy: str
    votes: Mapping[str, str] = field(default_factory=dict)
    counts: Mapping[str, int] = field(default_factory=dict)
    tied_player_ids: tuple[str, ...] = ()
    missing_voter_ids: tuple[str, ...] = ()
    eliminated_player_id: str | None = None

    def __post_init__(self) -> None:
        """Freeze vote mappings and ordered identifier collections."""
        object.__setattr__(self, "votes", frozen_mapping(self.votes))
        object.__setattr__(self, "counts", frozen_mapping(self.counts))
        object.__setattr__(self, "tied_player_ids", tuple(self.tied_player_ids))
        object.__setattr__(self, "missing_voter_ids", tuple(self.missing_voter_ids))


@dataclass(frozen=True)
class InspectionResult:
    """Private result of one seer inspection."""

    day: int
    seer_id: str
    target_id: str
    target_role: str
    target_faction: str


@dataclass(frozen=True)
class NightResult:
    """Resolved facts for one night phase."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: tuple[InspectionResult, ...] = ()

    def __post_init__(self) -> None:
        """Freeze inspection results."""
        object.__setattr__(self, "inspections", tuple(self.inspections))


@dataclass(frozen=True)
class SpeechRecord:
    """One accepted public speech."""

    day: int
    player_id: str
    message: str
    reason: str = ""

    def __post_init__(self) -> None:
        """Normalize speech identifiers and text."""
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        object.__setattr__(self, "message", non_blank(self.message, "message"))
        object.__setattr__(self, "reason", self.reason.strip())


@dataclass(frozen=True)
class WinResult:
    """Terminal outcome for one game."""

    winner: str
    reason: str
    day: int
    winning_player_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Normalize the outcome and freeze winning player IDs."""
        winner = non_blank(self.winner, "winner")
        if winner not in SUPPORTED_FACTIONS:
            raise ValueError(message_unsupported_faction(winner))
        if self.day < 1:
            raise ValueError("win result day must be at least 1.")
        player_ids = tuple(
            non_blank(value, "winning player id") for value in self.winning_player_ids
        )
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("winning player ids must be unique.")
        object.__setattr__(self, "winner", winner)
        object.__setattr__(self, "reason", non_blank(self.reason, "reason"))
        object.__setattr__(self, "winning_player_ids", player_ids)


@dataclass(frozen=True)
class GameHistory:
    """Immutable collection of resolved game history."""

    speeches: tuple[SpeechRecord, ...] = ()
    votes: tuple[VoteResult, ...] = ()
    nights: tuple[NightResult, ...] = ()

    def __post_init__(self) -> None:
        """Freeze all history collections."""
        object.__setattr__(self, "speeches", tuple(self.speeches))
        object.__setattr__(self, "votes", tuple(self.votes))
        object.__setattr__(self, "nights", tuple(self.nights))


@dataclass(frozen=True)
class PendingActions:
    """Unresolved actions hidden inside the aggregate state."""

    votes: Mapping[str, Action] = field(default_factory=dict)
    night_actions: Mapping[str, Action] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze unresolved vote and night action mappings."""
        object.__setattr__(self, "votes", frozen_mapping(self.votes))
        object.__setattr__(self, "night_actions", frozen_mapping(self.night_actions))


@dataclass(frozen=True)
class GameState:
    """Complete immutable snapshot of one game."""

    config: GameConfig
    phase: Phase
    day: int
    players: Mapping[str, Player]
    history: GameHistory = field(default_factory=GameHistory)
    pending_actions: PendingActions = field(default_factory=PendingActions)
    win_result: WinResult | None = None

    def __post_init__(self) -> None:
        """Freeze the snapshot and enforce aggregate reconstruction invariants."""
        phase = Phase(self.phase)
        players = dict(sorted(self.players.items(), key=lambda item: item[0]))
        if self.day < 1:
            raise ValueError("game day must be at least 1.")
        if len(players) != self.config.player_count:
            raise ValueError("player count must match the game configuration.")
        if any(key != player.id for key, player in players.items()):
            raise ValueError("player mapping keys must match player ids.")
        assigned_roles = Counter(player.role for player in players.values())
        if None in assigned_roles or assigned_roles != Counter(self.config.role_counts):
            raise ValueError("assigned roles must match configured role counts.")
        if (phase is Phase.FINISHED) != (self.win_result is not None):
            raise ValueError("finished phase and win result must be present together.")
        if self.win_result is not None:
            unknown_winners = set(self.win_result.winning_player_ids) - set(players)
            if unknown_winners:
                raise ValueError("winning player ids must belong to the game.")
            expected_winners = {
                player.id
                for player in players.values()
                if player.role is not None
                and self.config.roles.faction_for_role(player.role) == self.win_result.winner
            }
            if set(self.win_result.winning_player_ids) != expected_winners:
                raise ValueError("winning player ids must match the winning faction.")
            if self.win_result.day != self.day:
                raise ValueError("win result day must match the game day.")
        for actions in (self.pending_actions.votes, self.pending_actions.night_actions):
            if any(
                key != action.player_id or key not in players for key, action in actions.items()
            ):
                raise ValueError("pending action keys must identify a game player.")
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "players", frozen_mapping(players))

    @property
    def is_finished(self) -> bool:
        """Return whether the game has reached its terminal phase."""
        return self.phase is Phase.FINISHED

    @property
    def winner_id(self) -> str | None:
        """Return the canonical winning faction ID when decided."""
        return None if self.win_result is None else self.win_result.winner


@dataclass(frozen=True)
class GameView:
    """Immutable player-specific observation of a game."""

    phase: Phase
    day: int
    me: Player
    players: tuple[Player, ...]
    known_roles: Mapping[str, str] = field(default_factory=dict)
    available_actions: tuple[ActionType, ...] = ()
    legal_targets: Mapping[ActionType, tuple[str, ...]] = field(default_factory=dict)
    history: GameHistory = field(default_factory=GameHistory)
    win_result: WinResult | None = None

    def __post_init__(self) -> None:
        """Freeze visible collections and legal targets."""
        object.__setattr__(self, "players", tuple(self.players))
        object.__setattr__(self, "known_roles", frozen_mapping(self.known_roles))
        object.__setattr__(self, "available_actions", tuple(self.available_actions))
        object.__setattr__(
            self,
            "legal_targets",
            frozen_mapping({key: tuple(value) for key, value in self.legal_targets.items()}),
        )


@dataclass(frozen=True)
class GameEvent:
    """Immutable fact emitted after a successful state transition."""

    event_type: str
    phase: Phase | None = None
    day: int | None = None
    actor_id: str | None = None
    visibility: EventVisibility = EventVisibility.PUBLIC
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize the event type and deeply freeze its payload."""
        object.__setattr__(self, "event_type", non_blank(self.event_type, "event_type"))
        object.__setattr__(self, "phase", None if self.phase is None else Phase(self.phase))
        object.__setattr__(self, "visibility", EventVisibility(self.visibility))
        if self.day is not None and self.day < 1:
            raise ValueError("event day must be at least 1.")
        object.__setattr__(self, "actor_id", optional_non_blank(self.actor_id, "actor_id"))
        object.__setattr__(self, "payload", freeze_value(self.payload))


@dataclass(frozen=True)
class GameSetup:
    """Validated players used to create a game."""

    players: tuple[Player, ...]

    def __post_init__(self) -> None:
        """Freeze players and require unique identifiers."""
        players = tuple(self.players)
        if len({player.id for player in players}) != len(players):
            raise ValueError("player ids must be unique.")
        object.__setattr__(self, "players", players)


__all__ = [
    "ABILITY_GUARD",
    "ABILITY_INSPECT",
    "ABILITY_NIGHT_ATTACK",
    "ABILITY_PACK_KNOWLEDGE",
    "FACTION_VILLAGE",
    "FACTION_WEREWOLF",
    "SUPPORTED_FACTIONS",
    "AbilityDefinition",
    "Action",
    "ActionType",
    "EventVisibility",
    "GameConfig",
    "GameEvent",
    "GameHistory",
    "GameSetup",
    "GameState",
    "GameView",
    "InspectionResult",
    "LocalRules",
    "NightResult",
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
