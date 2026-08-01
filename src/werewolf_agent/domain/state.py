"""Immutable values for the deterministic headless game."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from werewolf_agent.domain._messages import (
    MESSAGE_PLAYER_COUNT_AT_LEAST_ONE,
    MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE,
    MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT,
    MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE,
    MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF,
    MESSAGE_ROLES_REQUIRED,
    message_role_count_must_be_zero_or_greater,
    message_unknown_role_in_role_counts,
    message_unsupported_abilities,
    message_unsupported_faction,
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
    """ゲームのlifecycle phaseを表す."""

    SETUP = "setup"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    FINISHED = "finished"


class PlayerStatus(StrEnum):
    """Playerの生存状態を表す."""

    ALIVE = "alive"
    DEAD = "dead"


class ActionType(StrEnum):
    """Domain coreが解釈する安定したaction種別を表す."""

    SPEECH = "speech"
    VOTE = "vote"
    USE_ABILITY = "use_ability"
    PASS = "pass"


class DiscussionRoundKind(StrEnum):
    """一日の議論内で進行するroundを表す."""

    OPENING = "opening"
    RESPONSE = "response"


class SubmissionMode(StrEnum):
    """Actionを公開前に集めるか一人ずつ処理するか表す."""

    SEALED = "sealed"
    ORDERED = "ordered"


class DiscussionPosition(StrEnum):
    """議論対象の命題に対する公開立場を表す."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    UNDECIDED = "undecided"


class DiscussionRelation(StrEnum):
    """一つの議論手と参照発言の関係を表す."""

    INDEPENDENT = "independent"
    ANSWER = "answer"
    SUPPORT = "support"
    CHALLENGE = "challenge"
    REVISE = "revise"


class EvidenceKind(StrEnum):
    """行動根拠として公開できる議論事実の種別を表す."""

    DISCUSSION = "discussion"
    DISCUSSION_PASS = "discussion_pass"


class EventVisibility(StrEnum):
    """Domain eventへ付与する可視性区分を表す."""

    PUBLIC = "public"
    PLAYER_PRIVATE = "player_private"
    DEBUG = "debug"


@dataclass(frozen=True)
class AbilityDefinition:
    """一つのbounded ability componentのimmutable設定を表す."""

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
    """一つのゲーム内のimmutableなplayer状態を表す."""

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
        """Playerが現在行動できるか返す."""
        return self.status is PlayerStatus.ALIVE


@dataclass(frozen=True)
class DiscussionStageConfig:
    """一つの議論stageの提出方式と参照規則を表す."""

    stage: DiscussionRoundKind
    submission_mode: SubmissionMode
    actor_order: str
    reference_stage: DiscussionRoundKind | None
    allowed_relations: tuple[DiscussionRelation, ...]

    def __post_init__(self) -> None:
        """Stage定義を正規化して相互整合を検証する."""
        object.__setattr__(self, "stage", DiscussionRoundKind(self.stage))
        object.__setattr__(self, "submission_mode", SubmissionMode(self.submission_mode))
        if self.actor_order not in {"rotating", "reverse_opening"}:
            raise ValueError(f"Unknown discussion actor order: {self.actor_order}")
        reference_stage = (
            DiscussionRoundKind(self.reference_stage) if self.reference_stage is not None else None
        )
        object.__setattr__(self, "reference_stage", reference_stage)
        relations = tuple(DiscussionRelation(item) for item in self.allowed_relations)
        if not relations or len(relations) != len(set(relations)):
            raise ValueError("allowed_relations must contain unique values")
        object.__setattr__(self, "allowed_relations", relations)
        if self.stage is DiscussionRoundKind.OPENING:
            if reference_stage is not None or relations != (DiscussionRelation.INDEPENDENT,):
                raise ValueError("opening stage must be independent and reference-free")
        elif reference_stage is not DiscussionRoundKind.OPENING:
            raise ValueError("response stage must reference opening")


DEFAULT_DISCUSSION_STAGES = (
    DiscussionStageConfig(
        DiscussionRoundKind.OPENING,
        SubmissionMode.SEALED,
        "rotating",
        None,
        (DiscussionRelation.INDEPENDENT,),
    ),
    DiscussionStageConfig(
        DiscussionRoundKind.RESPONSE,
        SubmissionMode.ORDERED,
        "reverse_opening",
        DiscussionRoundKind.OPENING,
        (
            DiscussionRelation.ANSWER,
            DiscussionRelation.SUPPORT,
            DiscussionRelation.CHALLENGE,
            DiscussionRelation.REVISE,
        ),
    ),
)


@dataclass(frozen=True)
class DiscussionConfig:
    """一局へ固定する議論規則を表す."""

    protocol_id: str = "structured_argument"
    message_max_chars: int = 200
    cycles_per_day: int = 1
    stages: tuple[DiscussionStageConfig, ...] = DEFAULT_DISCUSSION_STAGES

    def __post_init__(self) -> None:
        """議論protocol、発言長、サイクル数を検証する."""
        object.__setattr__(self, "protocol_id", non_blank(self.protocol_id, "protocol_id"))
        if not 1 <= self.message_max_chars <= 2000:
            raise ValueError("message_max_chars must be between 1 and 2000.")
        if not 1 <= self.cycles_per_day <= 10:
            raise ValueError("cycles_per_day must be between 1 and 10.")
        stages = tuple(self.stages)
        if tuple(stage.stage for stage in stages) != (
            DiscussionRoundKind.OPENING,
            DiscussionRoundKind.RESPONSE,
        ):
            raise ValueError("discussion stages must be opening then response")
        object.__setattr__(self, "stages", stages)


@dataclass(frozen=True)
class VotingConfig:
    """一局へ固定する投票規則を表す."""

    allow_self_vote: bool = False
    allow_revision: bool = False
    tie_resolution: str = "no_elimination"
    reason_max_chars: int = 120

    def __post_init__(self) -> None:
        """同票処理と理由長を検証する."""
        if self.tie_resolution not in {
            "no_elimination",
            "random_elimination",
            "revote",
        }:
            raise ValueError(f"Unknown vote tie resolution: {self.tie_resolution}")
        if not 1 <= self.reason_max_chars <= 1000:
            raise ValueError("reason_max_chars must be between 1 and 1000.")


@dataclass(frozen=True)
class NightConfig:
    """一局へ固定する夜行動規則を表す."""

    allow_action_revision: bool = False
    allow_pass: bool = True


@dataclass(frozen=True)
class LifecycleConfig:
    """一局へ固定するphase遷移と公開規則を表す."""

    starting_phase: str = "night"
    reveal_role_on_death: bool = False
    require_all_actions_before_advance: bool = True

    def __post_init__(self) -> None:
        """開始phaseを検証する."""
        if self.starting_phase not in {"night", "day_discussion"}:
            raise ValueError(f"Unknown starting phase: {self.starting_phase}")


@dataclass(frozen=True)
class RoleDefinition:
    """一つの役職のimmutableなfactionとability所属を表す."""

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
        """役職が指定したability IDを所有するか返す."""
        return ability in self.abilities


@dataclass(frozen=True)
class RoleCatalog:
    """設定済み役職定義のimmutable lookupを提供する."""

    roles: Mapping[str, RoleDefinition]

    def __post_init__(self) -> None:
        """Normalize role IDs and freeze the catalog."""
        roles = {non_blank(str(role_id), "role id"): value for role_id, value in self.roles.items()}
        if not roles:
            raise ValueError(MESSAGE_ROLES_REQUIRED)
        object.__setattr__(self, "roles", frozen_mapping(roles))

    def require_role(self, role: str) -> RoleDefinition:
        """設定済み役職を返し、未知のIDでは例外を返す."""
        return self.roles[role]

    def faction_for_role(self, role: str) -> str:
        """一つの役職に対する正規faction IDを返す."""
        return self.require_role(role).identity_faction

    def victory_team_for_role(self, role: str) -> str:
        """一つの役職が勝利するteamを返す."""
        return self.require_role(role).victory_team

    def role_has_ability(self, role: str | None, ability: str) -> bool:
        """割当済み役職がabilityを所有するか返す."""
        return role is not None and self.require_role(role).has_ability(ability)


@dataclass(frozen=True)
class GameConfig:
    """ゲーム状態へ埋め込む検証済みimmutable設定を表す."""

    player_count: int
    role_counts: Mapping[str, int]
    discussion: DiscussionConfig
    voting: VotingConfig
    night: NightConfig
    lifecycle: LifecycleConfig
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
            if self.lifecycle.starting_phase == "night"
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
    """Playerへ提示する一つのaction候補を表す."""

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
        """Actionの安定した合法target keyを返す."""
        return (
            f"{self.type.value}:{self.ability_id}"
            if self.ability_id is not None
            else self.type.value
        )


@dataclass(frozen=True)
class EvidenceFact:
    """行動根拠として選択できる一つの公開議論事実を表す."""

    evidence_id: str
    kind: EvidenceKind
    actor_id: str
    topic_id: str
    position: DiscussionPosition | None = None

    def __post_init__(self) -> None:
        """公開事実の識別子と構造値を正規化する."""
        object.__setattr__(self, "evidence_id", non_blank(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "kind", EvidenceKind(self.kind))
        object.__setattr__(self, "actor_id", non_blank(self.actor_id, "actor_id"))
        object.__setattr__(self, "topic_id", non_blank(self.topic_id, "topic_id"))
        object.__setattr__(
            self,
            "position",
            None if self.position is None else DiscussionPosition(self.position),
        )


@dataclass(frozen=True)
class DiscussionMove:
    """公開議論として提出する正規化された手を表す."""

    utterance: str
    topic_id: str
    position: DiscussionPosition
    relation: DiscussionRelation
    evidence_id: str | None = None
    response_to_id: str | None = None

    def __post_init__(self) -> None:
        """表示文、議論対象、立場、関係を正規化する."""
        object.__setattr__(self, "utterance", non_blank(self.utterance, "utterance"))
        object.__setattr__(self, "topic_id", non_blank(self.topic_id, "topic_id"))
        object.__setattr__(self, "position", DiscussionPosition(self.position))
        object.__setattr__(self, "relation", DiscussionRelation(self.relation))
        object.__setattr__(self, "evidence_id", optional_non_blank(self.evidence_id, "evidence_id"))
        object.__setattr__(
            self,
            "response_to_id",
            optional_non_blank(self.response_to_id, "response_to_id"),
        )


@dataclass(frozen=True)
class VoteIntent:
    """公開理由を伴う投票payloadを表す."""

    target_id: str
    reason: str
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        """投票先と公開理由を正規化する."""
        object.__setattr__(self, "target_id", non_blank(self.target_id, "target_id"))
        object.__setattr__(self, "reason", non_blank(self.reason, "reason"))
        object.__setattr__(self, "evidence_id", optional_non_blank(self.evidence_id, "evidence_id"))


@dataclass(frozen=True)
class UseAbilityIntent:
    """設定済み能力を使うpayloadを表す."""

    ability_id: str
    target_id: str | None = None

    def __post_init__(self) -> None:
        """能力IDと任意対象IDを正規化する."""
        object.__setattr__(self, "ability_id", non_blank(self.ability_id, "ability_id"))
        object.__setattr__(self, "target_id", optional_non_blank(self.target_id, "target_id"))


@dataclass(frozen=True)
class PassIntent:
    """payloadを持たない明示的な棄権を表す."""


ActionIntent = DiscussionMove | VoteIntent | UseAbilityIntent | PassIntent


@dataclass(frozen=True)
class Action:
    """ゲームaggregateが受理する型付きplayer intentを表す."""

    player_id: str
    intent: ActionIntent

    def __post_init__(self) -> None:
        """Player IDと対応可能なintent型を検証する."""
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        if not isinstance(self.intent, (DiscussionMove, VoteIntent, UseAbilityIntent, PassIntent)):
            raise TypeError("intent must be a supported action intent")

    @property
    def type(self) -> ActionType:
        """Intentに対応する安定action typeを返す."""
        if isinstance(self.intent, DiscussionMove):
            return ActionType.SPEECH
        if isinstance(self.intent, VoteIntent):
            return ActionType.VOTE
        if isinstance(self.intent, UseAbilityIntent):
            return ActionType.USE_ABILITY
        return ActionType.PASS

    @property
    def target_id(self) -> str | None:
        """対象player IDを持つintentなら返す."""
        return (
            self.intent.target_id
            if isinstance(self.intent, (VoteIntent, UseAbilityIntent))
            else None
        )

    @property
    def ability_id(self) -> str | None:
        """能力intentなら能力IDを返す."""
        return self.intent.ability_id if isinstance(self.intent, UseAbilityIntent) else None

    @property
    def utterance(self) -> str | None:
        """議論手なら表示用の自然文を返す."""
        return self.intent.utterance if isinstance(self.intent, DiscussionMove) else None

    @property
    def position(self) -> DiscussionPosition | None:
        """議論手なら対象命題への立場を返す."""
        return self.intent.position if isinstance(self.intent, DiscussionMove) else None

    @property
    def relation(self) -> DiscussionRelation | None:
        """議論手なら参照発言との関係を返す."""
        return self.intent.relation if isinstance(self.intent, DiscussionMove) else None

    @property
    def topic_id(self) -> str | None:
        """議論手なら議論対象player IDを返す."""
        return self.intent.topic_id if isinstance(self.intent, DiscussionMove) else None

    @property
    def evidence_id(self) -> str | None:
        """公開根拠を持つintentなら根拠IDを返す."""
        return (
            self.intent.evidence_id
            if isinstance(self.intent, (DiscussionMove, VoteIntent))
            else None
        )

    @property
    def response_to_id(self) -> str | None:
        """発言intentなら応答先の公開発言IDを返す."""
        return self.intent.response_to_id if isinstance(self.intent, DiscussionMove) else None

    @property
    def reason(self) -> str:
        """投票intentなら公開理由を返す."""
        return self.intent.reason if isinstance(self.intent, VoteIntent) else ""

    @property
    def is_night_action(self) -> bool:
        """Actionをnight phaseで解決するか返す."""
        return self.type in {ActionType.USE_ABILITY, ActionType.PASS}

    @classmethod
    def speech(
        cls,
        player_id: str,
        utterance: str,
        *,
        topic_id: str,
        position: DiscussionPosition,
        relation: DiscussionRelation,
        evidence_id: str | None = None,
        response_to_id: str | None = None,
    ) -> Self:
        """公開discussion actionを作成して返す."""
        return cls(
            player_id,
            DiscussionMove(
                utterance,
                topic_id,
                position,
                relation,
                evidence_id,
                response_to_id,
            ),
        )

    @classmethod
    def vote(
        cls,
        player_id: str,
        target_id: str,
        *,
        reason: str,
        evidence_id: str | None = None,
    ) -> Self:
        """生存player一人を対象とするvote actionを作成して返す."""
        return cls(player_id, VoteIntent(target_id, reason, evidence_id))

    @classmethod
    def use_ability(
        cls,
        player_id: str,
        ability_id: str,
        target_id: str | None = None,
    ) -> Self:
        """設定済みability actionを作成して返す."""
        return cls(player_id, UseAbilityIntent(ability_id, target_id))

    @classmethod
    def pass_(cls, player_id: str) -> Self:
        """明示的なno-op actionを作成して返す."""
        return cls(player_id, PassIntent())


@dataclass(frozen=True)
class VoteResolution:
    """Voting Policyが返すstate非変更Outcomeを表す."""

    day: int
    tie_break_policy: str
    votes: Mapping[str, str] = field(default_factory=dict)
    reasons: Mapping[str, str] = field(default_factory=dict)
    evidence_ids: Mapping[str, str] = field(default_factory=dict)
    counts: Mapping[str, int] = field(default_factory=dict)
    tied_player_ids: tuple[str, ...] = ()
    missing_voter_ids: tuple[str, ...] = ()
    eliminated_player_id: str | None = None
    round: int = 1
    requires_revote: bool = False

    def __post_init__(self) -> None:
        """投票Outcomeのmappingと順序付きcollectionを固定する."""
        object.__setattr__(self, "votes", frozen_mapping(self.votes))
        object.__setattr__(self, "reasons", frozen_mapping(self.reasons))
        object.__setattr__(self, "evidence_ids", frozen_mapping(self.evidence_ids))
        object.__setattr__(self, "counts", frozen_mapping(self.counts))
        object.__setattr__(self, "tied_player_ids", tuple(self.tied_player_ids))
        object.__setattr__(self, "missing_voter_ids", tuple(self.missing_voter_ids))


@dataclass(frozen=True)
class VoteResult(VoteResolution):
    """Gameが検証して確定した一回の投票履歴を表す."""


@dataclass(frozen=True)
class InspectionResult:
    """可視性を制御した一回の設定済みinspection結果を表す."""

    day: int
    player_id: str
    ability_id: str
    target_id: str
    target_role: str
    target_faction: str


@dataclass(frozen=True)
class NightResolution:
    """Night ability policyが返すstate非変更の解決Outcomeを表す."""

    attacked_player_ids: tuple[str, ...] = ()
    protected_player_ids: tuple[str, ...] = ()
    killed_player_ids: tuple[str, ...] = ()
    inspections: tuple[InspectionResult, ...] = ()
    passive_uses: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """順序付きcollectionをimmutableなtupleへ固定する."""
        object.__setattr__(self, "attacked_player_ids", tuple(self.attacked_player_ids))
        object.__setattr__(self, "protected_player_ids", tuple(self.protected_player_ids))
        object.__setattr__(self, "killed_player_ids", tuple(self.killed_player_ids))
        object.__setattr__(self, "inspections", tuple(self.inspections))
        object.__setattr__(
            self,
            "passive_uses",
            tuple((player_id, ability_id) for player_id, ability_id in self.passive_uses),
        )


@dataclass(frozen=True)
class DeathReaction:
    """一つの死亡反応が選んだ能力所有者と死亡対象を表す."""

    player_id: str
    ability_id: str
    target_id: str


@dataclass(frozen=True)
class DeathReactionResolution:
    """Ability policyが返す順序付き死亡反応Outcomeを表す."""

    reactions: tuple[DeathReaction, ...] = ()

    def __post_init__(self) -> None:
        """反応列をimmutableなtupleへ固定する."""
        object.__setattr__(self, "reactions", tuple(self.reactions))


@dataclass(frozen=True)
class KnowledgeClaim:
    """設定済みknowledge能力が一人について返すroleまたはfactionを表す."""

    player_id: str
    ability_id: str
    target_id: str
    role: str | None = None
    faction: str | None = None


@dataclass(frozen=True)
class KnowledgeResolution:
    """Ability policyが返すstate非変更の知識候補を表す."""

    claims: tuple[KnowledgeClaim, ...] = ()

    def __post_init__(self) -> None:
        """知識候補列をimmutableなtupleへ固定する."""
        object.__setattr__(self, "claims", tuple(self.claims))


@dataclass(frozen=True)
class NightResult:
    """一回のnight phaseで解決したfactを表す."""

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
    """受理された一つの公開speechを表す."""

    day: int
    speech_id: str
    round_id: str
    round_kind: DiscussionRoundKind
    player_id: str
    utterance: str
    topic_id: str
    position: DiscussionPosition
    relation: DiscussionRelation
    evidence_id: str | None = None
    response_to_id: str | None = None

    def __post_init__(self) -> None:
        """Normalize speech identifiers and text."""
        object.__setattr__(self, "speech_id", non_blank(self.speech_id, "speech_id"))
        object.__setattr__(self, "round_id", non_blank(self.round_id, "round_id"))
        object.__setattr__(self, "round_kind", DiscussionRoundKind(self.round_kind))
        object.__setattr__(self, "player_id", non_blank(self.player_id, "player_id"))
        object.__setattr__(self, "utterance", non_blank(self.utterance, "utterance"))
        object.__setattr__(self, "topic_id", non_blank(self.topic_id, "topic_id"))
        object.__setattr__(self, "position", DiscussionPosition(self.position))
        object.__setattr__(self, "relation", DiscussionRelation(self.relation))
        object.__setattr__(self, "evidence_id", optional_non_blank(self.evidence_id, "evidence_id"))
        object.__setattr__(
            self,
            "response_to_id",
            optional_non_blank(self.response_to_id, "response_to_id"),
        )
        if self.round_kind is DiscussionRoundKind.OPENING and self.response_to_id is not None:
            raise ValueError("opening speech cannot reference another speech")
        if self.round_kind is DiscussionRoundKind.RESPONSE and self.response_to_id is None:
            raise ValueError("response speech requires response_to_id")


@dataclass(frozen=True)
class DiscussionRound:
    """一つの議論roundの決定的な進行位置を表す."""

    round_id: str
    cycle: int
    kind: DiscussionRoundKind
    submission_mode: SubmissionMode
    actor_order: tuple[str, ...]
    cursor: int = 0
    reference_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Round方式、順序、参照を相互検証する."""
        object.__setattr__(self, "round_id", non_blank(self.round_id, "round_id"))
        if self.cycle < 1:
            raise ValueError("discussion cycle must be at least 1")
        object.__setattr__(self, "kind", DiscussionRoundKind(self.kind))
        object.__setattr__(self, "submission_mode", SubmissionMode(self.submission_mode))
        actor_order = tuple(non_blank(item, "actor_id") for item in self.actor_order)
        references = tuple(non_blank(item, "reference_id") for item in self.reference_ids)
        if not actor_order or len(actor_order) != len(set(actor_order)):
            raise ValueError("discussion actor_order must contain unique players")
        if not 0 <= self.cursor < len(actor_order):
            raise ValueError("discussion cursor is outside actor_order")
        if len(references) != len(set(references)):
            raise ValueError("discussion reference_ids must contain unique speeches")
        if self.kind is DiscussionRoundKind.OPENING:
            if self.submission_mode is not SubmissionMode.SEALED or references:
                raise ValueError("opening round must be sealed without references")
        elif self.submission_mode is not SubmissionMode.ORDERED or not references:
            raise ValueError("response round must be ordered with references")
        object.__setattr__(self, "actor_order", actor_order)
        object.__setattr__(self, "reference_ids", references)

    @property
    def current_actor_id(self) -> str | None:
        """順次roundで現在行動できるplayer IDを返す."""
        if self.submission_mode is SubmissionMode.SEALED or self.cursor >= len(self.actor_order):
            return None
        return self.actor_order[self.cursor]


@dataclass(frozen=True)
class DiscussionResolution:
    """Discussion Policyが返すstate非変更Outcomeを表す."""

    speeches: tuple[SpeechRecord, ...]
    next_round: DiscussionRound | None
    completed: bool

    def __post_init__(self) -> None:
        """完了状態と次roundの排他関係を検証する."""
        object.__setattr__(self, "speeches", tuple(self.speeches))
        if self.completed == (self.next_round is not None):
            raise ValueError("completed discussion must not define next_round")


@dataclass(frozen=True)
class DiscussionResult:
    """Gameが確定した一つの議論roundを表す."""

    day: int
    round_id: str
    kind: DiscussionRoundKind
    speech_ids: tuple[str, ...]
    passed_player_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """確定roundと公開発言IDを検証する."""
        if self.day < 1:
            raise ValueError("discussion result day must be at least 1")
        object.__setattr__(self, "round_id", non_blank(self.round_id, "round_id"))
        object.__setattr__(self, "kind", DiscussionRoundKind(self.kind))
        speech_ids = tuple(non_blank(item, "speech_id") for item in self.speech_ids)
        if len(speech_ids) != len(set(speech_ids)):
            raise ValueError("discussion result speech IDs must be unique")
        object.__setattr__(self, "speech_ids", speech_ids)
        passed = tuple(non_blank(item, "passed_player_id") for item in self.passed_player_ids)
        if len(passed) != len(set(passed)):
            raise ValueError("discussion result passed player IDs must be unique")
        object.__setattr__(self, "passed_player_ids", passed)


@dataclass(frozen=True)
class WinResult:
    """一つのゲームの終端結果を表す."""

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
class VisibleWinResult:
    """Player observationへ公開できる勝敗情報を表す."""

    winner: str
    reason: str
    day: int

    def __post_init__(self) -> None:
        """勝利陣営、理由、日数を公開値として検証する."""
        winner = non_blank(self.winner, "winner")
        if winner not in SUPPORTED_FACTIONS:
            raise ValueError(message_unsupported_faction(winner))
        if self.day < 1:
            raise ValueError("visible win result day must be at least 1.")
        object.__setattr__(self, "winner", winner)
        object.__setattr__(self, "reason", non_blank(self.reason, "reason"))


@dataclass(frozen=True)
class GameHistory:
    """解決済みゲーム履歴のimmutable collectionを表す."""

    speeches: tuple[SpeechRecord, ...] = ()
    discussions: tuple[DiscussionResult, ...] = ()
    votes: tuple[VoteResult, ...] = ()
    nights: tuple[NightResult, ...] = ()

    def __post_init__(self) -> None:
        """Freeze all history collections."""
        object.__setattr__(self, "speeches", tuple(self.speeches))
        object.__setattr__(self, "discussions", tuple(self.discussions))
        object.__setattr__(self, "votes", tuple(self.votes))
        object.__setattr__(self, "nights", tuple(self.nights))


@dataclass(frozen=True)
class PendingActions:
    """Aggregate状態内へ隠す未解決actionを表す."""

    votes: Mapping[str, Action] = field(default_factory=dict)
    night_actions: Mapping[str, Action] = field(default_factory=dict)
    discussion_actions: Mapping[str, Action] = field(default_factory=dict)
    discussion_round: DiscussionRound | None = None
    vote_round: int = 1
    revote_candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Freeze unresolved vote and night action mappings."""
        object.__setattr__(self, "votes", frozen_mapping(self.votes))
        object.__setattr__(self, "night_actions", frozen_mapping(self.night_actions))
        object.__setattr__(self, "discussion_actions", frozen_mapping(self.discussion_actions))
        object.__setattr__(self, "revote_candidates", tuple(self.revote_candidates))
        if self.vote_round not in {1, 2}:
            raise ValueError("vote_round must be 1 or 2.")
        if self.vote_round == 1 and self.revote_candidates:
            raise ValueError("first vote round cannot have revote candidates.")


@dataclass(frozen=True)
class GameState:
    """一つのゲームの完全なimmutable snapshotを表す."""

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
        for actions in (
            self.pending_actions.votes,
            self.pending_actions.night_actions,
            self.pending_actions.discussion_actions,
        ):
            if any(
                key != action.player_id or key not in players for key, action in actions.items()
            ):
                raise ValueError("pending action keys must identify a game player.")
        round_ = self.pending_actions.discussion_round
        if phase is Phase.DAY_DISCUSSION:
            if round_ is None and self.pending_actions.discussion_actions:
                raise ValueError("discussion actions require an active round")
            if round_ is not None and set(round_.actor_order) - set(players):
                raise ValueError("discussion actors must belong to the game")
        elif round_ is not None or self.pending_actions.discussion_actions:
            raise ValueError("discussion pending state is allowed only during day discussion")
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
        """ゲームが終端phaseへ到達したか返す."""
        return self.phase is Phase.FINISHED

    @property
    def winner_id(self) -> str | None:
        """勝者決定後に正規winning faction IDを返す."""
        return None if self.win_result is None else self.win_result.winner


@dataclass(frozen=True)
class GameView:
    """Playerごとのimmutableなゲームobservationを表す."""

    phase: Phase
    day: int
    me: Player
    players: tuple[Player, ...]
    known_roles: Mapping[str, str] = field(default_factory=dict)
    known_factions: Mapping[str, str] = field(default_factory=dict)
    available_actions: tuple[AvailableAction, ...] = ()
    legal_targets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    legal_evidence: Mapping[str, tuple[EvidenceFact, ...]] = field(default_factory=dict)
    action_text_limits: Mapping[str, int] = field(default_factory=dict)
    history: GameHistory = field(default_factory=GameHistory)
    discussion_round: DiscussionRound | None = None
    win_result: VisibleWinResult | None = None

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
        object.__setattr__(
            self,
            "legal_evidence",
            frozen_mapping({key: tuple(value) for key, value in self.legal_evidence.items()}),
        )
        action_text_limits = {
            non_blank(key, "action text limit key"): int(value)
            for key, value in self.action_text_limits.items()
        }
        if any(value < 1 for value in action_text_limits.values()):
            raise ValueError("action text limits must be positive")
        object.__setattr__(self, "action_text_limits", frozen_mapping(action_text_limits))


@dataclass(frozen=True)
class GameEvent:
    """状態遷移の成功後に生成するimmutable factを表す."""

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
    """ゲーム作成に使用する検証済みplayerを保持する."""

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
    "ActionIntent",
    "ActionType",
    "AvailableAction",
    "DeathReaction",
    "DeathReactionResolution",
    "DiscussionConfig",
    "DiscussionMove",
    "DiscussionPosition",
    "DiscussionRelation",
    "DiscussionResolution",
    "DiscussionResult",
    "DiscussionRound",
    "DiscussionRoundKind",
    "EventVisibility",
    "EvidenceFact",
    "EvidenceKind",
    "GameConfig",
    "GameEvent",
    "GameHistory",
    "GameSetup",
    "GameState",
    "GameView",
    "InspectionResult",
    "KnowledgeClaim",
    "KnowledgeResolution",
    "LifecycleConfig",
    "NightConfig",
    "NightResolution",
    "NightResult",
    "PassIntent",
    "PendingActions",
    "Phase",
    "Player",
    "PlayerStatus",
    "RoleCatalog",
    "RoleDefinition",
    "SpeechRecord",
    "SubmissionMode",
    "UseAbilityIntent",
    "VoteIntent",
    "VoteResolution",
    "VoteResult",
    "VotingConfig",
    "WinResult",
]
