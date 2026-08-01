"""完全なゲームsetupの標準ライブラリ契約を定義する."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from string import Formatter
from types import MappingProxyType
from typing import Final, Literal

from werewolf_agent.domain import RuleSetDefinition
from werewolf_agent.domain.state import (
    AbilityDefinition as DomainAbilityDefinition,
)
from werewolf_agent.domain.state import (
    DiscussionConfig,
    DiscussionKind,
    LifecycleConfig,
    NightConfig,
    Phase,
    RoleCatalog,
    VotingConfig,
)
from werewolf_agent.domain.state import (
    RoleDefinition as DomainRoleDefinition,
)
from werewolf_agent.setup.players import (
    PlayerGenerationDefinition,
    PlayerIdentityDefinition,
    PrivateStrategyDefinition,
    PublicPersonaDefinition,
)

SETUP_SCHEMA_VERSION: Final = "0.4.0"
FactionId = Literal["village", "werewolf", "fox"]

NARRATION_EVENT_IDS: Final = frozenset(
    {"game_started", "phase_started", "night_resolved", "vote_resolved", "game_finished"}
)
NARRATION_TEMPLATE_FIELDS: Final = frozenset(
    {
        "day",
        "phase",
        "phase_label",
        "actor",
        "player_count",
        "eliminated_player",
        "killed_player",
        "winner",
        "winner_label",
    }
)
ABILITY_KINDS: Final = frozenset(
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
ACTIVE_ABILITY_KINDS: Final = frozenset({"attack", "inspect", "protect", "eliminate"})
COMMON_ABILITY_FIELDS: Final = frozenset(
    {
        "kind",
        "phase",
        "target_policy",
        "start_day",
        "max_uses",
        "result_visibility",
        "resolution_priority",
        "allow_repeat_target",
        "enabled_first_night",
    }
)
KIND_FIELDS: Final = {
    "attack": frozenset({"tie_resolution"}),
    "inspect": frozenset({"result_detail"}),
    "protect": frozenset(),
    "eliminate": frozenset(),
    "knowledge": frozenset({"knowledge_mode", "result_detail"}),
    "death_reaction": frozenset(),
    "immunity": frozenset({"source_kinds"}),
    "vulnerability": frozenset({"source_kinds"}),
}


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return {str(key): item for key, item in value.items()}


def _strict(
    value: Mapping[str, object],
    required: set[str] | frozenset[str],
    name: str,
    *,
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required - optional)
    if missing:
        raise ValueError(f"{name} is missing required fields: {missing}")
    if extra:
        raise ValueError(f"{name} has extra fields: {extra}")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    return normalized


def _integer(value: object, name: str, *, minimum: int, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        upper = "" if maximum is None else f" and at most {maximum}"
        raise ValueError(f"{name} must be at least {minimum}{upper}")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _choice(value: object, name: str, choices: set[str] | frozenset[str]) -> str:
    selected = _text(value, name)
    if selected not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)}")
    return selected


def _sequence(value: object, name: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be an array")
    return tuple(value)


def _text_map(value: object, name: str) -> Mapping[str, str]:
    source = _mapping(value, name)
    return MappingProxyType(
        {_text(key, f"{name} id"): _text(item, name) for key, item in source.items()}
    )


@dataclass(frozen=True)
class RoleDefinition:
    """一つの役職の陣営とability参照を表す."""

    identity_faction: FactionId
    victory_team: FactionId
    abilities: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: object) -> RoleDefinition:
        """JSON互換mappingを検証して役職定義を返す."""
        source = _mapping(value, "role")
        _strict(source, {"identity_faction", "victory_team", "abilities"}, "role")
        abilities = tuple(
            _text(item, "ability id") for item in _sequence(source["abilities"], "abilities")
        )
        if len(abilities) != len(set(abilities)):
            raise ValueError("role abilities must be unique")
        return cls(
            identity_faction=_choice(
                source["identity_faction"], "identity_faction", {"village", "werewolf", "fox"}
            ),  # type: ignore[arg-type]
            victory_team=_choice(
                source["victory_team"], "victory_team", {"village", "werewolf", "fox"}
            ),  # type: ignore[arg-type]
            abilities=abilities,
        )

    def to_mapping(self) -> dict[str, object]:
        """JSON互換の正規化済み役職定義を返す."""
        return {
            "identity_faction": self.identity_faction,
            "victory_team": self.victory_team,
            "abilities": list(self.abilities),
        }


@dataclass(frozen=True)
class AbilityDefinition:
    """一つの実行可能または受動的なabilityを表す."""

    kind: str
    phase: str
    target_policy: str
    start_day: int
    max_uses: Literal["unlimited"] | int
    result_visibility: str
    resolution_priority: int
    allow_repeat_target: bool
    enabled_first_night: bool
    result_detail: str | None = None
    knowledge_mode: str | None = None
    tie_resolution: str | None = None
    source_kinds: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: object) -> AbilityDefinition:
        """JSON互換mappingをkind別に検証してability定義を返す."""
        source = _mapping(value, "ability")
        kind = _choice(source.get("kind"), "kind", ABILITY_KINDS)
        expected = COMMON_ABILITY_FIELDS | KIND_FIELDS[kind]
        _strict(source, expected, f"{kind} ability")
        phase = _choice(source["phase"], "phase", {"night", "day_discussion", "voting", "finished"})
        target_policy = _choice(
            source["target_policy"],
            "target_policy",
            {"none", "alive", "other_alive", "other_alive_non_faction"},
        )
        max_uses_value = source["max_uses"]
        max_uses: Literal["unlimited"] | int = (
            "unlimited"
            if max_uses_value == "unlimited"
            else _integer(max_uses_value, "max_uses", minimum=1)
        )
        result_visibility = _choice(
            source["result_visibility"], "result_visibility", {"private", "public", "none"}
        )
        allow_repeat_target = _boolean(source["allow_repeat_target"], "allow_repeat_target")
        enabled_first_night = _boolean(source["enabled_first_night"], "enabled_first_night")
        if kind in ACTIVE_ABILITY_KINDS and phase != "night":
            raise ValueError(f"{kind} abilities must run during night")
        if kind in ACTIVE_ABILITY_KINDS and target_policy == "none":
            raise ValueError(f"{kind} abilities require a target")
        if kind not in ACTIVE_ABILITY_KINDS and target_policy != "none":
            raise ValueError(f"{kind} abilities cannot define a target")
        if target_policy == "none" and not allow_repeat_target:
            raise ValueError("abilities without a target must allow repeat targets")
        if phase != "night" and not enabled_first_night:
            raise ValueError("enabled_first_night only applies to night abilities")
        if kind not in {"inspect", "knowledge"} and result_visibility != "none":
            raise ValueError(f"{kind} abilities do not produce a visible result")
        if kind == "knowledge" and max_uses != "unlimited":
            raise ValueError("knowledge abilities must use unlimited max_uses")
        if kind in {"immunity", "vulnerability"} and phase != "night":
            raise ValueError(f"{kind} abilities must run during night")
        if kind == "death_reaction" and phase not in {"night", "voting"}:
            raise ValueError("death_reaction abilities must run during night or voting")

        result_detail = None
        knowledge_mode = None
        tie_resolution = None
        source_kinds: tuple[str, ...] = ()
        if "result_detail" in source:
            result_detail = _choice(source["result_detail"], "result_detail", {"faction", "role"})
        if "knowledge_mode" in source:
            knowledge_mode = _choice(
                source["knowledge_mode"], "knowledge_mode", {"allies", "last_eliminated"}
            )
        if "tie_resolution" in source:
            tie_resolution = _choice(
                source["tie_resolution"], "tie_resolution", {"random_target", "no_action"}
            )
        if "source_kinds" in source:
            allowed_sources = (
                {"attack", "eliminate", "inspect"} if kind == "immunity" else {"inspect"}
            )
            source_kinds = tuple(
                _choice(item, "source_kind", allowed_sources)
                for item in _sequence(source["source_kinds"], "source_kinds")
            )
            if not source_kinds:
                raise ValueError("source_kinds must not be empty")
            if len(source_kinds) != len(set(source_kinds)):
                raise ValueError("source_kinds must be unique")
        return cls(
            kind=kind,
            phase=phase,
            target_policy=target_policy,
            start_day=_integer(source["start_day"], "start_day", minimum=1),
            max_uses=max_uses,
            result_visibility=result_visibility,
            resolution_priority=_integer(
                source["resolution_priority"], "resolution_priority", minimum=0, maximum=1000
            ),
            allow_repeat_target=allow_repeat_target,
            enabled_first_night=enabled_first_night,
            result_detail=result_detail,
            knowledge_mode=knowledge_mode,
            tie_resolution=tie_resolution,
            source_kinds=source_kinds,
        )

    def to_mapping(self) -> dict[str, object]:
        """JSON互換の正規化済みability定義を返す."""
        result: dict[str, object] = {
            "kind": self.kind,
            "phase": self.phase,
            "target_policy": self.target_policy,
            "start_day": self.start_day,
            "max_uses": self.max_uses,
            "result_visibility": self.result_visibility,
            "resolution_priority": self.resolution_priority,
            "allow_repeat_target": self.allow_repeat_target,
            "enabled_first_night": self.enabled_first_night,
        }
        for key in KIND_FIELDS[self.kind]:
            value = getattr(self, key)
            result[key] = list(value) if key == "source_kinds" else value
        return result


@dataclass(frozen=True)
class DiscussionDefinition:
    """一局で使用する議論方式と公開発言長を表す."""

    kind: str
    message_max_chars: int
    cycles_per_day: int = 1

    @classmethod
    def from_mapping(cls, value: object) -> DiscussionDefinition:
        """JSON互換mappingを検証して議論定義を返す."""
        source = _mapping(value, "discussion")
        _strict(
            source,
            {"kind", "message_max_chars"},
            "discussion",
            optional={"cycles_per_day"},
        )
        return cls(
            _choice(source["kind"], "kind", {"structured"}),
            _integer(source["message_max_chars"], "message_max_chars", minimum=1, maximum=2000),
            _integer(source.get("cycles_per_day", 1), "cycles_per_day", minimum=1, maximum=10),
        )

    def to_mapping(self) -> dict[str, object]:
        """永続化できるJSON互換mappingを返す."""
        return {
            "kind": self.kind,
            "message_max_chars": self.message_max_chars,
            "cycles_per_day": self.cycles_per_day,
        }


@dataclass(frozen=True)
class VotingDefinition:
    """一局で使用する投票規則を表す."""

    allow_self_vote: bool
    allow_revision: bool
    tie_resolution: str
    reason_max_chars: int

    @classmethod
    def from_mapping(cls, value: object) -> VotingDefinition:
        """JSON互換mappingを検証して投票定義を返す."""
        source = _mapping(value, "voting")
        _strict(
            source,
            {"allow_self_vote", "allow_revision", "tie_resolution", "reason_max_chars"},
            "voting",
        )
        return cls(
            _boolean(source["allow_self_vote"], "allow_self_vote"),
            _boolean(source["allow_revision"], "allow_revision"),
            _choice(
                source["tie_resolution"],
                "tie_resolution",
                {"no_elimination", "random_elimination", "revote"},
            ),
            _integer(source["reason_max_chars"], "reason_max_chars", minimum=1, maximum=1000),
        )

    def to_mapping(self) -> dict[str, object]:
        """永続化できるJSON互換mappingを返す."""
        return {
            "allow_self_vote": self.allow_self_vote,
            "allow_revision": self.allow_revision,
            "tie_resolution": self.tie_resolution,
            "reason_max_chars": self.reason_max_chars,
        }


@dataclass(frozen=True)
class NightDefinition:
    """一局で使用する夜行動規則を表す."""

    allow_action_revision: bool

    @classmethod
    def from_mapping(cls, value: object) -> NightDefinition:
        """JSON互換mappingを検証して夜行動定義を返す."""
        source = _mapping(value, "night")
        _strict(source, {"allow_action_revision"}, "night")
        return cls(_boolean(source["allow_action_revision"], "allow_action_revision"))

    def to_mapping(self) -> dict[str, object]:
        """永続化できるJSON互換mappingを返す."""
        return {"allow_action_revision": self.allow_action_revision}


@dataclass(frozen=True)
class LifecycleDefinition:
    """一局で使用するphase遷移と死亡公開規則を表す."""

    starting_phase: str
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool

    @classmethod
    def from_mapping(cls, value: object) -> LifecycleDefinition:
        """JSON互換mappingを検証して進行定義を返す."""
        source = _mapping(value, "lifecycle")
        _strict(
            source,
            {"starting_phase", "reveal_role_on_death", "require_all_actions_before_advance"},
            "lifecycle",
        )
        return cls(
            _choice(source["starting_phase"], "starting_phase", {"night", "day_discussion"}),
            _boolean(source["reveal_role_on_death"], "reveal_role_on_death"),
            _boolean(
                source["require_all_actions_before_advance"],
                "require_all_actions_before_advance",
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        """永続化できるJSON互換mappingを返す."""
        return {
            "starting_phase": self.starting_phase,
            "reveal_role_on_death": self.reveal_role_on_death,
            "require_all_actions_before_advance": self.require_all_actions_before_advance,
        }


@dataclass(frozen=True)
class MechanicsDefinition:
    """一つのゲームで選択する決定的なmechanicsを表す."""

    role_counts: Mapping[str, int]
    roles: Mapping[str, RoleDefinition]
    abilities: Mapping[str, AbilityDefinition]
    discussion: DiscussionDefinition
    voting: VotingDefinition
    night: NightDefinition
    lifecycle: LifecycleDefinition

    @classmethod
    def from_mapping(cls, value: object) -> MechanicsDefinition:
        """JSON互換mappingを参照整合性まで検証してmechanicsを返す."""
        source = _mapping(value, "mechanics")
        _strict(
            source,
            {"role_counts", "roles", "abilities", "discussion", "voting", "night", "lifecycle"},
            "mechanics",
        )
        role_counts = MappingProxyType(
            {
                _text(key, "role id"): _integer(count, "role count", minimum=1)
                for key, count in _mapping(source["role_counts"], "role_counts").items()
            }
        )
        roles = MappingProxyType(
            {
                _text(key, "role id"): RoleDefinition.from_mapping(item)
                for key, item in _mapping(source["roles"], "roles").items()
            }
        )
        abilities = MappingProxyType(
            {
                _text(key, "ability id"): AbilityDefinition.from_mapping(item)
                for key, item in _mapping(source["abilities"], "abilities").items()
            }
        )
        if not role_counts:
            raise ValueError("role_counts must select at least one player")
        if set(role_counts) != set(roles):
            raise ValueError("roles must exactly match selected role_counts")
        referenced = {ability for role in roles.values() for ability in role.abilities}
        if referenced != set(abilities):
            raise ValueError("abilities must exactly match role references")
        if not {"village", "werewolf"}.issubset({role.identity_faction for role in roles.values()}):
            raise ValueError("selected roles require village and werewolf identity factions")
        return cls(
            role_counts=role_counts,
            roles=roles,
            abilities=abilities,
            discussion=DiscussionDefinition.from_mapping(source["discussion"]),
            voting=VotingDefinition.from_mapping(source["voting"]),
            night=NightDefinition.from_mapping(source["night"]),
            lifecycle=LifecycleDefinition.from_mapping(source["lifecycle"]),
        )

    def to_mapping(self) -> dict[str, object]:
        """JSON互換の正規化済みmechanicsを返す."""
        return {
            "role_counts": dict(self.role_counts),
            "roles": {key: item.to_mapping() for key, item in self.roles.items()},
            "abilities": {key: item.to_mapping() for key, item in self.abilities.items()},
            "discussion": self.discussion.to_mapping(),
            "voting": self.voting.to_mapping(),
            "night": self.night.to_mapping(),
            "lifecycle": self.lifecycle.to_mapping(),
        }

    def to_rule_definition(self) -> RuleSetDefinition:
        """Domainが実行する型付きRule Definitionへ変換する."""
        return RuleSetDefinition(
            player_count=sum(self.role_counts.values()),
            role_counts=self.role_counts,
            discussion=DiscussionConfig(
                kind=DiscussionKind(self.discussion.kind),
                message_max_chars=self.discussion.message_max_chars,
                cycles_per_day=self.discussion.cycles_per_day,
            ),
            voting=VotingConfig(**self.voting.to_mapping()),  # type: ignore[arg-type]
            night=NightConfig(**self.night.to_mapping()),  # type: ignore[arg-type]
            lifecycle=LifecycleConfig(**self.lifecycle.to_mapping()),  # type: ignore[arg-type]
            roles=RoleCatalog(
                {
                    role_id: DomainRoleDefinition(
                        identity_faction=role.identity_faction,
                        victory_team=role.victory_team,
                        abilities=role.abilities,
                    )
                    for role_id, role in self.roles.items()
                }
            ),
            abilities={
                ability_id: DomainAbilityDefinition(
                    kind=ability.kind,
                    phase=Phase(ability.phase),
                    target_policy=ability.target_policy,
                    start_day=ability.start_day,
                    max_uses=None if ability.max_uses == "unlimited" else ability.max_uses,
                    result_visibility=ability.result_visibility,
                    resolution_priority=ability.resolution_priority,
                    allow_repeat_target=ability.allow_repeat_target,
                    enabled_first_night=ability.enabled_first_night,
                    result_detail=ability.result_detail,
                    knowledge_mode=ability.knowledge_mode,
                    tie_resolution=ability.tie_resolution,
                    source_kinds=ability.source_kinds,
                )
                for ability_id, ability in self.abilities.items()
            },
        )


@dataclass(frozen=True)
class ThemeDefinition:
    """表示専用の用語と公開narrationを表す."""

    id: str
    name: str
    summary: str
    premise: str
    role_names: Mapping[str, str]
    role_objectives: Mapping[str, str]
    role_descriptions: Mapping[str, str]
    faction_names: Mapping[str, str]
    ability_names: Mapping[str, str]
    ability_descriptions: Mapping[str, str]
    action_names: Mapping[str, str]
    phase_names: Mapping[str, str]
    narration_enabled: bool
    narration: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_mapping(cls, value: object) -> ThemeDefinition:
        """JSON互換mappingをnarration構文まで検証してthemeを返す."""
        source = _mapping(value, "theme")
        fields = {
            "id",
            "name",
            "summary",
            "premise",
            "role_names",
            "role_objectives",
            "role_descriptions",
            "faction_names",
            "ability_names",
            "ability_descriptions",
            "action_names",
            "phase_names",
            "narration_enabled",
            "narration",
        }
        _strict(source, fields, "theme")
        narration: dict[str, tuple[str, ...]] = {}
        for key, templates in _mapping(source["narration"], "narration").items():
            group = tuple(
                _text(template, "narration template")
                for template in _sequence(templates, "narration templates")
            )
            if not group:
                raise ValueError("narration template groups must not be empty")
            for template in group:
                try:
                    unknown = _narration_fields(template) - NARRATION_TEMPLATE_FIELDS
                except ValueError as exc:
                    raise ValueError("narration template has invalid format syntax") from exc
                if unknown:
                    raise ValueError(f"narration template has unknown fields: {sorted(unknown)}")
            narration[_text(key, "narration id")] = group
        enabled = _boolean(source["narration_enabled"], "narration_enabled")
        if enabled and not narration:
            raise ValueError("enabled narration requires at least one template group")
        if enabled and set(narration) != NARRATION_EVENT_IDS:
            raise ValueError("enabled narration must cover every supported event")
        return cls(
            id=_text(source["id"], "theme id"),
            name=_text(source["name"], "theme name"),
            summary=_text(source["summary"], "theme summary"),
            premise=_text(source["premise"], "theme premise"),
            role_names=_text_map(source["role_names"], "role_names"),
            role_objectives=_text_map(source["role_objectives"], "role_objectives"),
            role_descriptions=_text_map(source["role_descriptions"], "role_descriptions"),
            faction_names=_text_map(source["faction_names"], "faction_names"),
            ability_names=_text_map(source["ability_names"], "ability_names"),
            ability_descriptions=_text_map(source["ability_descriptions"], "ability_descriptions"),
            action_names=_text_map(source["action_names"], "action_names"),
            phase_names=_text_map(source["phase_names"], "phase_names"),
            narration_enabled=enabled,
            narration=MappingProxyType(narration),
        )

    def to_mapping(self) -> dict[str, object]:
        """JSON互換の正規化済みthemeを返す."""
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "premise": self.premise,
            "role_names": dict(self.role_names),
            "role_objectives": dict(self.role_objectives),
            "role_descriptions": dict(self.role_descriptions),
            "faction_names": dict(self.faction_names),
            "ability_names": dict(self.ability_names),
            "ability_descriptions": dict(self.ability_descriptions),
            "action_names": dict(self.action_names),
            "phase_names": dict(self.phase_names),
            "narration_enabled": self.narration_enabled,
            "narration": {key: list(value) for key, value in self.narration.items()},
        }


def _narration_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, format_spec, _ in Formatter().parse(template):
        if field_name is not None:
            fields.add(field_name)
        if format_spec:
            fields.update(_narration_fields(format_spec))
    return fields


@dataclass(frozen=True)
class GameSetupDocument:
    """同じ入力から同じゲーム条件を構築する完全setup文書を表す."""

    schema_version: str
    mechanics: MechanicsDefinition
    theme: ThemeDefinition
    player_generation: PlayerGenerationDefinition

    @classmethod
    def from_mapping(cls, value: object) -> GameSetupDocument:
        """JSON互換mappingを検証し、immutableな完全setupへ変換する."""
        source = _mapping(value, "setup")
        _strict(
            source,
            {"schema_version", "mechanics", "theme", "player_generation"},
            "setup",
        )
        schema_version = _text(source["schema_version"], "schema_version")
        if schema_version != SETUP_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SETUP_SCHEMA_VERSION}")
        mechanics = MechanicsDefinition.from_mapping(source["mechanics"])
        theme = ThemeDefinition.from_mapping(source["theme"])
        generation = _player_generation(source["player_generation"])
        document = cls(schema_version, mechanics, theme, generation)
        document._validate_coverage()
        return document

    def _validate_coverage(self) -> None:
        roles = set(self.mechanics.roles)
        abilities = set(self.mechanics.abilities)
        factions: set[str] = {
            str(faction)
            for role in self.mechanics.roles.values()
            for faction in (role.identity_faction, role.victory_team)
        }
        coverage = {
            "role_names": set(self.theme.role_names),
            "role_objectives": set(self.theme.role_objectives),
            "role_descriptions": set(self.theme.role_descriptions),
            "ability_names": set(self.theme.ability_names),
            "ability_descriptions": set(self.theme.ability_descriptions),
            "faction_names": set(self.theme.faction_names),
            "action_names": set(self.theme.action_names),
            "phase_names": set(self.theme.phase_names),
        }
        expected: dict[str, set[str]] = {
            "role_names": roles,
            "role_objectives": roles,
            "role_descriptions": roles,
            "ability_names": abilities,
            "ability_descriptions": abilities,
            "faction_names": factions,
            "action_names": {"speech", "vote", "use_ability", "pass"},
            "phase_names": {"night", "day_discussion", "voting", "finished"},
        }
        failures = {
            key: sorted(expected[key] ^ actual)
            for key, actual in coverage.items()
            if actual != expected[key]
        }
        if failures:
            raise ValueError(f"theme coverage must exactly match mechanics: {failures}")
        if len(self.player_generation.identities) < sum(self.mechanics.role_counts.values()):
            raise ValueError("player identities must cover the selected player count")

    def to_mapping(self) -> dict[str, object]:
        """永続化とchecksumに使う正規JSON互換mappingを返す."""
        return {
            "schema_version": self.schema_version,
            "mechanics": self.mechanics.to_mapping(),
            "theme": self.theme.to_mapping(),
            "player_generation": _player_generation_mapping(self.player_generation),
        }

    def to_rule_definition(self) -> RuleSetDefinition:
        """Domainが実行する型付きRule Definitionへ変換する."""
        return self.mechanics.to_rule_definition()


def rule_definition_from_values(
    *,
    player_count: int,
    role_counts: Mapping[str, int],
    discussion: Mapping[str, object],
    voting: Mapping[str, object],
    night: Mapping[str, object],
    lifecycle: Mapping[str, object],
    roles: Mapping[str, Mapping[str, object]],
    abilities: Mapping[str, Mapping[str, object]],
) -> RuleSetDefinition:
    """個別の検証済み値からDomain Rule Definitionを構築する."""
    mechanics = MechanicsDefinition.from_mapping(
        {
            "role_counts": dict(role_counts),
            "discussion": dict(discussion),
            "voting": dict(voting),
            "night": dict(night),
            "lifecycle": dict(lifecycle),
            "roles": {key: dict(value) for key, value in roles.items()},
            "abilities": {key: dict(value) for key, value in abilities.items()},
        }
    )
    if sum(mechanics.role_counts.values()) != player_count:
        raise ValueError("player_count must match role_counts")
    return mechanics.to_rule_definition()


def _player_generation(value: object) -> PlayerGenerationDefinition:
    source = _mapping(value, "player_generation")
    _strict(
        source,
        {"identities", "public_personas", "private_strategies"},
        "player_generation",
    )
    identities = []
    for item in _sequence(source["identities"], "identities"):
        row = _mapping(item, "identity")
        _strict(row, {"name", "age_min", "age_max", "gender"}, "identity")
        identities.append(
            PlayerIdentityDefinition(
                _text(row["name"], "name"),
                _integer(row["age_min"], "age_min", minimum=18, maximum=120),
                _integer(row["age_max"], "age_max", minimum=18, maximum=120),
                _text(row["gender"], "gender"),
            )
        )
    personas = []
    for item in _sequence(source["public_personas"], "public_personas"):
        row = _mapping(item, "public_persona")
        _strict(row, {"personality", "speaking_style"}, "public_persona")
        personas.append(
            PublicPersonaDefinition(
                _text(row["personality"], "personality"),
                _text(row["speaking_style"], "speaking_style"),
            )
        )
    strategies = []
    for item in _sequence(source["private_strategies"], "private_strategies"):
        row = _mapping(item, "private_strategy")
        _strict(
            row,
            {"reasoning_style", "risk_tolerance", "evidence_focus"},
            "private_strategy",
        )
        strategies.append(
            PrivateStrategyDefinition(
                _text(row["reasoning_style"], "reasoning_style"),
                _choice(
                    row["risk_tolerance"],
                    "risk_tolerance",
                    {"low", "medium", "high"},
                ),  # type: ignore[arg-type]
                _text(row["evidence_focus"], "evidence_focus"),
            )
        )
    return PlayerGenerationDefinition(tuple(identities), tuple(personas), tuple(strategies))


def _player_generation_mapping(value: PlayerGenerationDefinition) -> dict[str, object]:
    return {
        "identities": [
            {
                "name": item.name,
                "age_min": item.age_min,
                "age_max": item.age_max,
                "gender": item.gender,
            }
            for item in value.identities
        ],
        "public_personas": [
            {"personality": item.personality, "speaking_style": item.speaking_style}
            for item in value.public_personas
        ],
        "private_strategies": [
            {
                "reasoning_style": item.reasoning_style,
                "risk_tolerance": item.risk_tolerance,
                "evidence_focus": item.evidence_focus,
            }
            for item in value.private_strategies
        ],
    }


__all__ = [
    "ABILITY_KINDS",
    "SETUP_SCHEMA_VERSION",
    "AbilityDefinition",
    "DiscussionDefinition",
    "GameSetupDocument",
    "LifecycleDefinition",
    "MechanicsDefinition",
    "NightDefinition",
    "RoleDefinition",
    "ThemeDefinition",
    "VotingDefinition",
    "rule_definition_from_values",
]
