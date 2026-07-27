"""Immutable values for the deterministic headless game."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

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
FACTION_FOX = "fox"
SUPPORTED_FACTIONS = frozenset({FACTION_VILLAGE, FACTION_WEREWOLF, FACTION_FOX})
SUPPORTED_ABILITY_KINDS = frozenset(
    {
        "attack",
        "inspect",
        "protect",
        "eliminate",
        "knowledge",
        "death_reaction",
        "immunity",
        "vulnerability",
    }
)


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
    """Stable action envelopes understood by the domain core."""

    SPEECH = "speech"
    VOTE = "vote"
    USE_ABILITY = "use_ability"
    PASS = "pass"


class EventVisibility(StrEnum):
    """Visibility classes attached to domain events."""

    PUBLIC = "public"
    PLAYER_PRIVATE = "player_private"
    DEBUG = "debug"


@dataclass(frozen=True)
class AbilityDefinition:
    """Immutable configuration for one bounded ability component."""

    kind: str
    phase: Phase
    target_policy: str
    start_day: int
    max_uses: int | None
    result_visibility: str
    resolution_priority: int
    allow_repeat_target: bool
    enabled_first_night: bool
    result_detail: str | None
    knowledge_mode: str | None
    tie_resolution: str | None
    source_kinds: tuple[str, ...]

    def __post_init__(self) -> None:
        """Normalize the action type and optional ability reference."""
        """Normalize values and reject unsupported component combinations."""
        kind = non_blank(self.kind, "kind")
        if kind not in SUPPORTED_ABILITY_KINDS:
            raise ValueError(f"Unknown ability kind: {kind}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "phase", Phase(self.phase))
        object.__setattr__(self, "target_policy", non_blank(self.target_policy, "target_policy"))
        object.__setattr__(self, "source_kinds", tuple(self.source_kinds))
        if self.start_day < 1:
            raise ValueError("start_day must be at least 1.")
        if self.target_policy not in {
            "none",
            "alive",
            "other_alive",
            "other_alive_non_faction",
        }:
            raise ValueError(f"Unknown ability target policy: {self.target_policy}")
        if self.max_uses is not None and self.max_uses < 1:
            raise ValueError("max_uses must be at least 1 when configured.")
        if self.result_visibility not in {"private", "public", "none"}:
            raise ValueError(f"Unknown result visibility: {self.result_visibility}")
        if not 0 <= self.resolution_priority <= 1000:
            raise ValueError("resolution_priority must be between 0 and 1000.")
        active_kinds = {"attack", "inspect", "protect", "eliminate"}
        if kind in active_kinds and self.phase is not Phase.NIGHT:
            raise ValueError(f"Ability kind {kind} is only supported during the night phase.")
        if kind in active_kinds and self.target_policy == "none":
            raise ValueError(f"Ability kind {kind} requires a target policy.")
        if kind not in active_kinds and self.target_policy != "none":
            raise ValueError(f"Passive ability kind {kind} cannot define a target policy.")
        if kind in {"inspect", "knowledge"} and self.result_detail not in {
            "faction",
            "role",
        }:
            raise ValueError(f"Ability kind {kind} requires result_detail.")
        if kind not in {"inspect", "knowledge"} and self.result_detail is not None:
            raise ValueError(f"Ability kind {kind} cannot define result_detail.")
        if self.knowledge_mode not in {None, "allies", "last_eliminated"}:
            raise ValueError(f"Unknown knowledge mode: {self.knowledge_mode}")
        if kind == "knowledge" and self.knowledge_mode is None:
            raise ValueError("Knowledge abilities require knowledge_mode.")
        if kind != "knowledge" and self.knowledge_mode is not None:
            raise ValueError(f"Ability kind {kind} cannot define knowledge_mode.")
        if kind == "attack" and self.tie_resolution not in {"random_target", "no_action"}:
            raise ValueError("Attack abilities require tie_resolution.")
        if kind != "attack" and self.tie_resolution is not None:
            raise ValueError(f"Ability kind {kind} cannot define tie_resolution.")
        if kind not in {"immunity", "vulnerability"} and self.source_kinds:
            raise ValueError(f"Ability kind {kind} cannot define source_kinds.")
        unknown_sources = sorted(set(self.source_kinds) - SUPPORTED_ABILITY_KINDS)
        if unknown_sources:
            raise ValueError(f"Unknown ability source kinds: {unknown_sources}")
        if len(self.source_kinds) != len(set(self.source_kinds)):
            raise ValueError("Ability source kinds must be unique.")
        supported_sources = {
            "immunity": {"attack", "eliminate", "inspect"},
            "vulnerability": {"inspect"},
        }
        if kind in supported_sources:
            if not self.source_kinds:
                raise ValueError(f"Ability kind {kind} requires source_kinds.")
            unsupported_sources = sorted(set(self.source_kinds) - supported_sources[kind])
            if unsupported_sources:
                raise ValueError(
                    f"Ability kind {kind} cannot react to source kinds: {unsupported_sources}"
                )
            if self.phase is not Phase.NIGHT:
                raise ValueError(f"Ability kind {kind} is only supported during the night phase.")
        if kind == "death_reaction" and self.phase not in {Phase.NIGHT, Phase.VOTING}:
            raise ValueError(
                "Ability kind death_reaction is only supported during night or voting."
            )


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
    vote_tie_resolution: str
    starting_phase: str
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool = True

    def __post_init__(self) -> None:
        """Validate mutually dependent local rule values."""
        if not 0 <= self.day_speech_limit_per_player <= 100:
            raise ValueError("day_speech_limit_per_player must be between 0 and 100.")
        if self.vote_tie_resolution not in {
            "no_elimination",
            "random_elimination",
            "revote",
        }:
            raise ValueError(f"Unknown vote tie resolution: {self.vote_tie_resolution}")
        if self.starting_phase not in {"night", "day_discussion"}:
            raise ValueError(f"Unknown starting phase: {self.starting_phase}")


@dataclass(frozen=True)
class RoleDefinition:
    """Immutable faction and ability membership for one role."""

    identity_faction: str
    victory_team: str
    abilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize the faction and unique ability IDs."""
        identity_faction = non_blank(self.identity_faction, "identity_faction")
        victory_team = non_blank(self.victory_team, "victory_team")
        if identity_faction not in SUPPORTED_FACTIONS:
            raise ValueError(message_unsupported_faction(identity_faction))
        if victory_team not in SUPPORTED_FACTIONS:
            raise ValueError(message_unsupported_faction(victory_team))
        abilities = tuple(non_blank(item, "ability") for item in self.abilities)
        if len(set(abilities)) != len(abilities):
            raise ValueError(MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE)
        object.__setattr__(self, "identity_faction", identity_faction)
        object.__setattr__(self, "victory_team", victory_team)
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
        return self.require_role(role).identity_faction

    def victory_team_for_role(self, role: str) -> str:
        """Return the team that wins with one role."""
        return self.require_role(role).victory_team

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
        phase_order = (
            (Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.VOTING)
            if self.rules.starting_phase == "night"
            else (Phase.DAY_DISCUSSION, Phase.VOTING, Phase.NIGHT)
        )
        object.__setattr__(self, "phase_order", phase_order)
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
class AvailableAction:
    """One action option exposed to a player."""

    type: ActionType
    ability_id: str | None = None

    def __post_init__(self) -> None:
        """Normalize and validate the optional ability reference."""
        object.__setattr__(self, "type", ActionType(self.type))
        object.__setattr__(self, "ability_id", optional_non_blank(self.ability_id, "ability_id"))
        if (self.type is ActionType.USE_ABILITY) != (self.ability_id is not None):
            raise ValueError("Only use_ability actions define ability_id.")

    @property
    def key(self) -> str:
        """Return the stable legal-target key for this action."""
        return (
            f"{self.type.value}:{self.ability_id}"
            if self.ability_id is not None
            else self.type.value
        )


@dataclass(frozen=True)
class Action:
    """Validated player intent accepted by the game aggregate."""

    type: ActionType
    player_id: str
    reason: str = ""
    target_id: str | None = None
    ability_id: str | None = None
    message: str | None = None
    focus_id: str | None = None
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        """Normalize action fields and enforce payload shape by action type."""
        object.__setattr__(self, "type", ActionType(self.type))
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "target_id", optional_non_blank(self.target_id, "target_id"))
        object.__setattr__(self, "ability_id", optional_non_blank(self.ability_id, "ability_id"))
        object.__setattr__(self, "message", optional_non_blank(self.message, "message"))
        object.__setattr__(self, "focus_id", optional_non_blank(self.focus_id, "focus_id"))
        object.__setattr__(self, "evidence_id", optional_non_blank(self.evidence_id, "evidence_id"))
        if self.type is ActionType.SPEECH:
            if self.message is None:
                raise ValueError(MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE)
            if self.target_id is not None:
                raise ValueError(MESSAGE_SPEECH_ACTION_FORBIDS_TARGET)
            if self.ability_id is not None:
                raise ValueError("Speech actions cannot define ability_id.")
        elif self.type is ActionType.VOTE:
            if self.focus_id is not None or self.evidence_id is not None:
                raise ValueError("Public speech references are allowed only for speech actions.")
            if self.target_id is None:
                raise ValueError(message_target_required(self.type.value, "actions"))
            if self.message is not None:
                raise ValueError(message_message_not_allowed(self.type.value, "actions"))
            if self.ability_id is not None:
                raise ValueError("Vote actions cannot define ability_id.")
        elif self.type is ActionType.USE_ABILITY:
            if self.ability_id is None:
                raise ValueError("use_ability requires ability_id.")
            if (
                self.message is not None
                or self.focus_id is not None
                or self.evidence_id is not None
            ):
                raise ValueError("Ability actions accept only ability_id, target_id, and reason.")
        elif self.type is ActionType.PASS:
            if (
                self.target_id is not None
                or self.ability_id is not None
                or self.message is not None
                or self.focus_id is not None
                or self.evidence_id is not None
            ):
                raise ValueError(MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD)
        else:
            raise ValueError(message_unsupported_type(self.type.value, "action"))

    @property
    def is_night_action(self) -> bool:
        """Return whether this action is resolved during the night phase."""
        return self.type in {ActionType.USE_ABILITY, ActionType.PASS}

    @classmethod
    def speech(
        cls,
        player_id: str,
        message: str,
        *,
        focus_id: str | None = None,
        evidence_id: str | None = None,
    ) -> Self:
        """Create a public speech action."""
        return cls(
            ActionType.SPEECH,
            player_id,
            message=message,
            focus_id=focus_id,
            evidence_id=evidence_id,
        )

    @classmethod
    def vote(cls, player_id: str, target_id: str, *, reason: str = "") -> Self:
        """Create a vote action against one living player."""
        return cls(ActionType.VOTE, player_id, reason=reason, target_id=target_id)

    @classmethod
    def use_ability(
        cls,
        player_id: str,
        ability_id: str,
        target_id: str | None = None,
        *,
        reason: str = "",
    ) -> Self:
        """Create one configured ability action."""
        return cls(
            ActionType.USE_ABILITY,
            player_id,
            reason=reason,
            target_id=target_id,
            ability_id=ability_id,
        )

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
    round: int = 1
    requires_revote: bool = False

    def __post_init__(self) -> None:
        """Freeze vote mappings and ordered identifier collections."""
        object.__setattr__(self, "votes", frozen_mapping(self.votes))
        object.__setattr__(self, "counts", frozen_mapping(self.counts))
        object.__setattr__(self, "tied_player_ids", tuple(self.tied_player_ids))
        object.__setattr__(self, "missing_voter_ids", tuple(self.missing_voter_ids))


@dataclass(frozen=True)
class InspectionResult:
    """Visibility-controlled result of one configured inspection."""

    day: int
    player_id: str
    ability_id: str
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
    killed_player_ids: tuple[str, ...] = ()
    inspections: tuple[InspectionResult, ...] = ()
    ability_targets: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze inspection results."""
        object.__setattr__(self, "inspections", tuple(self.inspections))
        object.__setattr__(
            self,
            "ability_targets",
            frozen_mapping(
                {
                    non_blank(player_id, "ability target player id"): frozen_mapping(
                        {
                            non_blank(ability_id, "ability target id"): non_blank(
                                target_id, "ability target player id"
                            )
                            for ability_id, target_id in targets.items()
                        }
                    )
                    for player_id, targets in self.ability_targets.items()
                }
            ),
        )
        killed_ids = tuple(self.killed_player_ids)
        if self.killed_player_id is not None and not killed_ids:
            killed_ids = (self.killed_player_id,)
        object.__setattr__(self, "killed_player_ids", killed_ids)


@dataclass(frozen=True)
class SpeechRecord:
    """One accepted public speech."""

    day: int
    player_id: str
    message: str
    reason: str = ""
    focus_id: str | None = None
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        """Normalize speech identifiers and text."""
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        object.__setattr__(self, "message", non_blank(self.message, "message"))
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "focus_id", optional_non_blank(self.focus_id, "focus_id"))
        object.__setattr__(self, "evidence_id", optional_non_blank(self.evidence_id, "evidence_id"))


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
    vote_round: int = 1
    revote_candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Freeze unresolved vote and night action mappings."""
        object.__setattr__(self, "votes", frozen_mapping(self.votes))
        object.__setattr__(self, "night_actions", frozen_mapping(self.night_actions))
        object.__setattr__(self, "revote_candidates", tuple(self.revote_candidates))
        if self.vote_round not in {1, 2}:
            raise ValueError("vote_round must be 1 or 2.")
        if self.vote_round == 1 and self.revote_candidates:
            raise ValueError("first vote round cannot have revote candidates.")


@dataclass(frozen=True)
class GameState:
    """Complete immutable snapshot of one game."""

    config: GameConfig
    phase: Phase
    day: int
    players: Mapping[str, Player]
    history: GameHistory = field(default_factory=GameHistory)
    pending_actions: PendingActions = field(default_factory=PendingActions)
    ability_uses: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
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
                and self.config.roles.victory_team_for_role(player.role) == self.win_result.winner
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
        ability_uses = {
            non_blank(player_id, "ability use player id"): frozen_mapping(
                {
                    non_blank(ability_id, "ability use id"): int(count)
                    for ability_id, count in uses.items()
                }
            )
            for player_id, uses in self.ability_uses.items()
        }
        if set(ability_uses) - set(players):
            raise ValueError("ability use player ids must belong to the game.")
        if any(count < 0 for uses in ability_uses.values() for count in uses.values()):
            raise ValueError("ability use counts cannot be negative.")
        object.__setattr__(self, "ability_uses", frozen_mapping(ability_uses))

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
    known_factions: Mapping[str, str] = field(default_factory=dict)
    available_actions: tuple[AvailableAction, ...] = ()
    legal_targets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    history: GameHistory = field(default_factory=GameHistory)
    win_result: WinResult | None = None

    def __post_init__(self) -> None:
        """Freeze visible collections and legal targets."""
        object.__setattr__(self, "players", tuple(self.players))
        object.__setattr__(self, "known_roles", frozen_mapping(self.known_roles))
        object.__setattr__(self, "known_factions", frozen_mapping(self.known_factions))
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
    "FACTION_VILLAGE",
    "FACTION_WEREWOLF",
    "SUPPORTED_ABILITY_KINDS",
    "SUPPORTED_FACTIONS",
    "AbilityDefinition",
    "Action",
    "ActionType",
    "AvailableAction",
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
