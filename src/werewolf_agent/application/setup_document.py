"""Portable, validated definition of one complete game setup."""

from __future__ import annotations

from string import Formatter
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.application.constants import (
    NARRATION_EVENT_IDS,
    NARRATION_TEMPLATE_FIELDS,
)
from werewolf_agent.application.validation import non_blank
from werewolf_agent.application.versions import SETUP_SCHEMA_VERSION
from werewolf_agent.setup import PlayerGenerationDefinition

FactionId = Literal["village", "werewolf", "fox"]
RoleCount = Annotated[int, Field(ge=1)]
AbilityKind = Literal[
    "attack",
    "inspect",
    "protect",
    "eliminate",
    "knowledge",
    "death_reaction",
    "immunity",
    "vulnerability",
]
ImmunitySourceKind = Literal["attack", "eliminate", "inspect"]
VulnerabilitySourceKind = Literal["inspect"]
TargetPolicy = Literal["none", "alive", "other_alive", "other_alive_non_faction"]


class ApplicationModel(BaseModel):
    """Strict immutable setup value."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RoleDefinition(ApplicationModel):
    """一つの役職のfaction所属とability構成を表す."""

    identity_faction: FactionId
    victory_team: FactionId
    abilities: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("abilities")
    @classmethod
    def normalize_abilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """重複のない正規化済みability参照を返す."""
        abilities = tuple(non_blank(item, "ability id") for item in value)
        if len(set(abilities)) != len(abilities):
            raise ValueError("role abilities must be unique")
        return abilities


class AbilityComponent(ApplicationModel):
    """Fields shared by every bounded ability component."""

    kind: AbilityKind
    phase: Literal["night", "day_discussion", "voting", "finished"]
    target_policy: TargetPolicy
    start_day: int = Field(ge=1)
    max_uses: Literal["unlimited"] | Annotated[int, Field(ge=1)]
    result_visibility: Literal["private", "public", "none"]
    resolution_priority: int = Field(ge=0, le=1000)
    allow_repeat_target: bool
    enabled_first_night: bool

    @model_validator(mode="after")
    def validate_common_shape(self) -> Self:
        active = {"attack", "inspect", "protect", "eliminate"}
        if self.kind in active and self.phase != "night":
            raise ValueError(f"{self.kind} abilities must run during night")
        if self.kind in active and self.target_policy == "none":
            raise ValueError(f"{self.kind} abilities require a target")
        if self.kind not in active and self.target_policy != "none":
            raise ValueError(f"{self.kind} abilities cannot define a target")
        if self.target_policy == "none" and not self.allow_repeat_target:
            raise ValueError("abilities without a target must allow repeat targets")
        if self.phase != "night" and not self.enabled_first_night:
            raise ValueError("enabled_first_night only applies to night abilities")
        if self.kind not in {"inspect", "knowledge"} and self.result_visibility != "none":
            raise ValueError(f"{self.kind} abilities do not produce a visible result")
        if self.kind == "knowledge" and self.max_uses != "unlimited":
            raise ValueError("knowledge abilities must use unlimited max_uses")
        if self.kind in {"immunity", "vulnerability"} and self.phase != "night":
            raise ValueError(f"{self.kind} abilities must run during night")
        if self.kind == "death_reaction" and self.phase not in {"night", "voting"}:
            raise ValueError("death_reaction abilities must run during night or voting")
        return self


class AttackAbility(AbilityComponent):
    """Night phaseに対象を攻撃するabilityを表す."""

    kind: Literal["attack"]
    tie_resolution: Literal["random_target", "no_action"]


class InspectAbility(AbilityComponent):
    """対象のfactionまたは役職を調査するabilityを表す."""

    kind: Literal["inspect"]
    result_detail: Literal["faction", "role"]


class ProtectAbility(AbilityComponent):
    """対象を攻撃から保護するabilityを表す."""

    kind: Literal["protect"]


class EliminateAbility(AbilityComponent):
    """対象を除外するabilityを表す."""

    kind: Literal["eliminate"]


class KnowledgeAbility(AbilityComponent):
    """開始時または進行中に知識を与えるabilityを表す."""

    kind: Literal["knowledge"]
    knowledge_mode: Literal["allies", "last_eliminated"]
    result_detail: Literal["faction", "role"]


class DeathReactionAbility(AbilityComponent):
    """死亡時の追加処理を定義するabilityを表す."""

    kind: Literal["death_reaction"]


class ImmunityAbility(AbilityComponent):
    """指定した作用元への耐性を定義するabilityを表す."""

    kind: Literal["immunity"]
    source_kinds: Annotated[tuple[ImmunitySourceKind, ...], Field(min_length=1)]

    @field_validator("source_kinds")
    @classmethod
    def validate_source_kinds(
        cls, value: tuple[ImmunitySourceKind, ...]
    ) -> tuple[ImmunitySourceKind, ...]:
        """重複のない耐性元種別を返す."""
        if len(value) != len(set(value)):
            raise ValueError("immunity source_kinds must be unique")
        return value


class VulnerabilityAbility(AbilityComponent):
    """指定した作用元への弱点を定義するabilityを表す."""

    kind: Literal["vulnerability"]
    source_kinds: Annotated[tuple[VulnerabilitySourceKind, ...], Field(min_length=1)]

    @field_validator("source_kinds")
    @classmethod
    def validate_source_kinds(
        cls, value: tuple[VulnerabilitySourceKind, ...]
    ) -> tuple[VulnerabilitySourceKind, ...]:
        """重複のない弱点元種別を返す."""
        if len(value) != len(set(value)):
            raise ValueError("vulnerability source_kinds must be unique")
        return value


AbilityDefinition = Annotated[
    AttackAbility
    | InspectAbility
    | ProtectAbility
    | EliminateAbility
    | KnowledgeAbility
    | DeathReactionAbility
    | ImmunityAbility
    | VulnerabilityAbility,
    Field(discriminator="kind"),
]


class LocalRulesDefinition(ApplicationModel):
    """Ability componentが所有しないゲーム全体の動作を表す."""

    day_speech_limit_per_player: int = Field(ge=0, le=100)
    allow_self_vote: bool
    allow_vote_revision: bool
    allow_night_action_revision: bool
    vote_tie_resolution: Literal["no_elimination", "random_elimination", "revote"]
    starting_phase: Literal["night", "day_discussion"]
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class MechanicsDefinition(ApplicationModel):
    """一つのゲームで選択する決定的なmechanicsを表す."""

    role_counts: dict[str, RoleCount]
    roles: dict[str, RoleDefinition]
    abilities: dict[str, AbilityDefinition]
    rules: LocalRulesDefinition

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("role_counts")
    @classmethod
    def normalize_role_counts(cls, value: dict[str, int]) -> dict[str, int]:
        """正規化済み役職IDをkeyとする役職数を返す."""
        return {non_blank(str(key), "role id"): count for key, count in value.items()}

    @field_validator("roles", "abilities")
    @classmethod
    def normalize_definition_ids(cls, value: dict[str, object]) -> dict[str, object]:
        """正規化済みIDをkeyとするcomponent定義を返す."""
        return {non_blank(str(key), "definition id"): item for key, item in value.items()}

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """役職数、ability参照、componentの意味を検証する."""
        if not self.role_counts:
            raise ValueError("role_counts must select at least one player")
        selected_roles = set(self.role_counts)
        if selected_roles != set(self.roles):
            raise ValueError("roles must exactly match selected role_counts")
        referenced = {ability_id for role in self.roles.values() for ability_id in role.abilities}
        if referenced != set(self.abilities):
            raise ValueError("abilities must exactly match role references")
        factions = {role.identity_faction for role in self.roles.values()}
        if not {"village", "werewolf"}.issubset(factions):
            raise ValueError("selected roles require village and werewolf identity factions")
        return self


class ThemeDefinition(ApplicationModel):
    """表示専用の用語と公開narrationを表す."""

    id: str
    name: str
    summary: str
    premise: str
    role_names: dict[str, str]
    role_objectives: dict[str, str]
    role_descriptions: dict[str, str]
    faction_names: dict[str, str]
    ability_names: dict[str, str]
    ability_descriptions: dict[str, str]
    action_names: dict[str, str]
    phase_names: dict[str, str]
    narration_enabled: bool
    narration: dict[str, tuple[str, ...]]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "summary", "premise")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """空でないtheme識別textを返す."""
        return non_blank(value, "theme text")

    @field_validator(
        "role_names",
        "role_objectives",
        "role_descriptions",
        "faction_names",
        "ability_names",
        "ability_descriptions",
        "action_names",
        "phase_names",
    )
    @classmethod
    def normalize_terms(cls, value: dict[str, str]) -> dict[str, str]:
        """正規化済みIDとtextを持つ表示用語を返す."""
        return {
            non_blank(str(key), "theme term id"): non_blank(text, "theme term")
            for key, text in value.items()
        }

    @field_validator("narration")
    @classmethod
    def normalize_narration(cls, value: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        """正規化済みevent IDをkeyとするnarration templateを返す."""
        normalized: dict[str, tuple[str, ...]] = {}
        for key, templates in value.items():
            narration_id = non_blank(str(key), "narration id")
            if not templates:
                raise ValueError("narration template groups must not be empty")
            normalized_templates: list[str] = []
            for template in templates:
                normalized_template = non_blank(template, "narration template")
                try:
                    fields = _narration_fields(normalized_template)
                except ValueError as exc:
                    raise ValueError("narration template has invalid format syntax") from exc
                unknown_fields = sorted(fields - NARRATION_TEMPLATE_FIELDS)
                if unknown_fields:
                    raise ValueError(f"narration template has unknown fields: {unknown_fields}")
                normalized_templates.append(normalized_template)
            normalized[narration_id] = tuple(normalized_templates)
        return normalized

    @model_validator(mode="after")
    def validate_narration(self) -> Self:
        """有効なnarration groupとtemplate placeholderを検証する."""
        if self.narration_enabled and not self.narration:
            raise ValueError("enabled narration requires at least one template group")
        if self.narration_enabled and set(self.narration) != NARRATION_EVENT_IDS:
            raise ValueError("enabled narration must cover every supported event")
        return self


def _narration_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, format_spec, _ in Formatter().parse(template):
        if field_name is not None:
            fields.add(field_name)
        if format_spec:
            fields.update(_narration_fields(format_spec))
    return fields


class GameSetupDocument(ApplicationModel):
    """全application境界が受理するportableな完全setupを表す."""

    schema_version: Literal["0.2.0"]
    mechanics: MechanicsDefinition
    theme: ThemeDefinition
    player_generation: PlayerGenerationDefinition

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        """選択したmechanicsをthemeとplayer poolが網羅することを要求する."""
        roles = set(self.mechanics.roles)
        abilities = set(self.mechanics.abilities)
        factions = {
            str(faction)
            for role in self.mechanics.roles.values()
            for faction in (role.identity_faction, role.victory_team)
        }
        required_actions = {"speech", "vote", "use_ability", "pass"}
        required_phases = {"night", "day_discussion", "voting", "finished"}
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
            "action_names": required_actions,
            "phase_names": required_phases,
        }
        failures = {
            key: sorted(expected[key] ^ values)
            for key, values in coverage.items()
            if values != expected[key]
        }
        if failures:
            raise ValueError(f"theme coverage must exactly match mechanics: {failures}")
        player_count = sum(self.mechanics.role_counts.values())
        if len(self.player_generation.identities) < player_count:
            raise ValueError("player identities must cover the selected player count")
        return self


class TemplateSetupSelection(ApplicationModel):
    """Selection of one packaged setup template."""

    mode: Literal["template"]
    template_id: str


class SavedSetupSelection(ApplicationModel):
    """Selection of one immutable saved setup revision."""

    mode: Literal["saved"]
    setup_id: str
    revision: int = Field(ge=1)


class InlineSetupSelection(ApplicationModel):
    """Selection carrying one complete inline setup document."""

    mode: Literal["inline"]
    document: GameSetupDocument


GameSetupSelection = Annotated[
    TemplateSetupSelection | SavedSetupSelection | InlineSetupSelection,
    Field(discriminator="mode"),
]


__all__ = [
    "SETUP_SCHEMA_VERSION",
    "AbilityDefinition",
    "GameSetupDocument",
    "GameSetupSelection",
    "InlineSetupSelection",
    "LocalRulesDefinition",
    "MechanicsDefinition",
    "RoleDefinition",
    "SavedSetupSelection",
    "TemplateSetupSelection",
    "ThemeDefinition",
]
