"""application definition models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.application.constants import (
    MAX_CHARACTER_AGE,
    MAX_DAY_SPEECH_LIMIT_PER_PLAYER,
    MAX_DIFFICULTY,
    MIN_CHARACTER_AGE,
    MIN_DAY_SPEECH_LIMIT_PER_PLAYER,
    MIN_DIFFICULTY,
    MIN_PLAYER_COUNT,
    MIN_ROLE_COUNT,
)
from werewolf_agent.application.messages import (
    MESSAGE_ALLOWED_ROLES_MUST_BE_UNIQUE,
    MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE,
    MESSAGE_DEFAULT_ROLE_COUNT_KEYS_POSITIVE,
    MESSAGE_DEFAULT_ROLE_COUNTS_REQUIRED,
    MESSAGE_LOCAL_RULE_TIE_RULE_EXACTLY_ONE,
    MESSAGE_NARRATION_TEMPLATES_REQUIRED,
    MESSAGE_PLAYER_PROFILE_NAMES_MUST_BE_UNIQUE,
    MESSAGE_PLAYERS_REQUIRED,
    MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE,
    MESSAGE_ROLES_REQUIRED,
    MESSAGE_SETUP_PRESET_ROLE_COUNTS_REQUIRED,
    message_default_role_counts_must_define_player_count,
    message_default_role_counts_must_sum,
    message_default_role_counts_unknown_roles,
    message_definition_references_unknown_ids,
)
from werewolf_agent.contracts.validation import non_blank

RoleCount = Annotated[int, Field(ge=MIN_ROLE_COUNT)]


class _DefinitionModel(BaseModel):
    """Base model for immutable application definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalRulesDefinition(_DefinitionModel):
    """Local rule flags used by the game core."""

    day_speech_limit_per_player: int = Field(
        ge=MIN_DAY_SPEECH_LIMIT_PER_PLAYER,
        le=MAX_DAY_SPEECH_LIMIT_PER_PLAYER,
    )
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

    @model_validator(mode="after")
    def validate_tie_resolution(self) -> Self:
        """Ensure one tie-resolution behavior is active."""
        enabled = [
            self.enable_no_elimination_on_tie,
            self.enable_random_elimination_on_tie,
        ]
        if enabled.count(True) != 1:
            raise ValueError(MESSAGE_LOCAL_RULE_TIE_RULE_EXACTLY_ONE)
        return self


class AbilityDefinition(_DefinitionModel):
    """Validated behavior and presentation values for one registered ability."""

    phase: str
    action: str
    validation_policy: str
    resolution_policy: str
    start_day: int = Field(ge=1)
    label: str
    description: str
    target_policy: str
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    @field_validator(
        "phase",
        "action",
        "validation_policy",
        "resolution_policy",
        "label",
        "description",
        "target_policy",
    )
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized ability metadata text."""
        return non_blank(value, str(info.field_name))


class RoleDefinition(_DefinitionModel):
    """Role faction and abilities."""

    faction: str
    abilities: tuple[str, ...] = ()
    label: str | None = None
    description: str | None = None
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    @field_validator("faction")
    @classmethod
    def validate_faction(cls, value: str) -> str:
        """Return a normalized faction id."""
        return non_blank(value, "faction")

    @field_validator("label", "description")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        """Return normalized optional display text."""
        if value is None:
            return None
        return non_blank(value, "role display text")

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return normalized unique ability ids."""
        abilities = tuple(non_blank(item, "ability") for item in value)
        if len(set(abilities)) != len(abilities):
            raise ValueError(MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE)
        return abilities


class CustomRoleDefinition(_DefinitionModel):
    """Session-scoped role definition supplied by a game API caller."""

    id: str
    name: str
    faction: str
    abilities: list[str] = Field(default_factory=list)
    description: str = ""
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    @field_validator("id", "name", "faction")
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized custom role text."""
        return non_blank(value, str(info.field_name))

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """Return normalized optional role description."""
        return value.strip()

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, value: list[str]) -> list[str]:
        """Return normalized unique ability ids."""
        abilities = [non_blank(item, "ability") for item in value]
        if len(set(abilities)) != len(abilities):
            raise ValueError(MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE)
        return abilities


class NarrationEventDefinition(_DefinitionModel):
    """Public-safe narration templates for one event type."""

    templates: tuple[str, ...]

    @field_validator("templates")
    @classmethod
    def validate_templates(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return non-empty public narration templates."""
        templates = tuple(non_blank(item, "narration template") for item in value)
        if not templates:
            raise ValueError(MESSAGE_NARRATION_TEMPLATES_REQUIRED)
        return templates


class NarrationProfileDefinition(_DefinitionModel):
    """Narration templates keyed by public event type."""

    events: dict[str, NarrationEventDefinition] = Field(default_factory=dict)

    @field_validator("events")
    @classmethod
    def validate_events(
        cls,
        value: dict[str, NarrationEventDefinition],
    ) -> dict[str, NarrationEventDefinition]:
        """Return narration events keyed by normalized event type."""
        return {non_blank(str(key), "narration event type"): item for key, item in value.items()}


class ScenarioDefinition(_DefinitionModel):
    """Scenario background used for setup display, narration, and LLM premise."""

    label: str
    summary: str
    prompt_premise: str
    narration_profile: str
    recommended_setup_preset: str | None = None
    allowed_roles: tuple[str, ...] = ()

    @field_validator("label", "summary", "prompt_premise", "narration_profile")
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized scenario text."""
        return non_blank(value, str(info.field_name))

    @field_validator("recommended_setup_preset")
    @classmethod
    def validate_optional_preset(cls, value: str | None) -> str | None:
        """Return normalized optional preset id."""
        if value is None:
            return None
        return non_blank(value, "recommended_setup_preset")

    @field_validator("allowed_roles")
    @classmethod
    def validate_allowed_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return normalized unique allowed role ids."""
        roles = tuple(non_blank(item, "allowed role") for item in value)
        if len(set(roles)) != len(roles):
            raise ValueError(MESSAGE_ALLOWED_ROLES_MUST_BE_UNIQUE)
        return roles


class SetupPresetDefinition(_DefinitionModel):
    """Named setup preset composed from scenario, role counts, and rules."""

    label: str
    scenario_id: str
    role_counts: dict[str, RoleCount]

    @field_validator("label", "scenario_id")
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized setup preset text."""
        return non_blank(value, str(info.field_name))

    @field_validator("role_counts")
    @classmethod
    def validate_role_counts(cls, value: dict[str, RoleCount]) -> dict[str, RoleCount]:
        """Return role counts keyed by normalized role id."""
        counts = {
            non_blank(str(role_id), "role count role id"): count for role_id, count in value.items()
        }
        if sum(counts.values()) < 1:
            raise ValueError(MESSAGE_SETUP_PRESET_ROLE_COUNTS_REQUIRED)
        return counts


class RuleCompositionDefinition(_DefinitionModel):
    """Registered policy ids and phase order used by the game core."""

    phases: tuple[str, ...] = ("night", "day_discussion", "voting")
    action_policy: str = "standard"
    resolution_policy: str = "standard"
    phase_policy: str = "required_actions"
    victory_policy: str = "faction_balance"
    visibility_policy: str = "standard"

    @field_validator("phases")
    @classmethod
    def validate_phases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require each supported playable phase exactly once."""
        phases = tuple(non_blank(phase, "phase") for phase in value)
        if set(phases) != {"night", "day_discussion", "voting"} or len(phases) != 3:
            raise ValueError("phases must contain night, day_discussion, and voting exactly once")
        return phases

    @field_validator(
        "action_policy",
        "resolution_policy",
        "phase_policy",
        "victory_policy",
        "visibility_policy",
    )
    @classmethod
    def validate_policy_id(cls, value: str, info: Any) -> str:
        """Return a normalized registered policy id."""
        return non_blank(value, str(info.field_name))


class GameRuleDefinitions(_DefinitionModel):
    """Game rule definition resource."""

    local_rules: LocalRulesDefinition
    composition: RuleCompositionDefinition = Field(default_factory=RuleCompositionDefinition)


class GameRoleDefinitions(_DefinitionModel):
    """Game role definition resource."""

    roles: dict[str, RoleDefinition] = Field(default_factory=dict)
    default_role_counts: dict[int, dict[str, RoleCount]]

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: dict[str, RoleDefinition]) -> dict[str, RoleDefinition]:
        """Return roles keyed by normalized role id."""
        roles = {
            non_blank(str(role_id), "role id"): definition for role_id, definition in value.items()
        }
        if not roles:
            raise ValueError(MESSAGE_ROLES_REQUIRED)
        return roles

    @field_validator("default_role_counts", mode="before")
    @classmethod
    def normalize_default_count_keys(cls, value: object) -> object:
        """Return role count defaults keyed by integer player count."""
        if not isinstance(value, Mapping):
            return value
        return {int(str(player_count)): counts for player_count, counts in value.items()}

    @model_validator(mode="after")
    def validate_default_role_counts(self) -> Self:
        """Ensure default role counts reference known roles and match their player count."""
        if not self.default_role_counts:
            raise ValueError(MESSAGE_DEFAULT_ROLE_COUNTS_REQUIRED)
        role_ids = set(self.roles)
        for player_count, counts in self.default_role_counts.items():
            if player_count < MIN_PLAYER_COUNT:
                raise ValueError(MESSAGE_DEFAULT_ROLE_COUNT_KEYS_POSITIVE)
            unknown = sorted(set(counts) - role_ids)
            if unknown:
                raise ValueError(message_default_role_counts_unknown_roles(unknown))
            if sum(counts.values()) != player_count:
                raise ValueError(message_default_role_counts_must_sum(player_count))
        return self

    def default_counts_for(self, player_count: int) -> dict[str, int]:
        """Return configured default role counts for one player count."""
        try:
            return dict(self.default_role_counts[player_count])
        except KeyError as exc:
            raise ValueError(
                message_default_role_counts_must_define_player_count(player_count)
            ) from exc


class GameCatalogDefinitions(_DefinitionModel):
    """Game setup catalog values that do not belong to the deterministic core."""

    abilities: dict[str, AbilityDefinition] = Field(default_factory=dict)
    scenarios: dict[str, ScenarioDefinition] = Field(default_factory=dict)
    narration_profiles: dict[str, NarrationProfileDefinition] = Field(default_factory=dict)
    setup_presets: dict[str, SetupPresetDefinition] = Field(default_factory=dict)

    @field_validator("abilities")
    @classmethod
    def validate_abilities(
        cls,
        value: dict[str, AbilityDefinition],
    ) -> dict[str, AbilityDefinition]:
        """Return ability metadata keyed by normalized ability id."""
        return {non_blank(str(key), "ability id"): item for key, item in value.items()}

    @field_validator("scenarios")
    @classmethod
    def validate_scenarios(
        cls,
        value: dict[str, ScenarioDefinition],
    ) -> dict[str, ScenarioDefinition]:
        """Return scenarios keyed by normalized scenario id."""
        return {non_blank(str(key), "scenario id"): item for key, item in value.items()}

    @field_validator("narration_profiles")
    @classmethod
    def validate_narration_profiles(
        cls,
        value: dict[str, NarrationProfileDefinition],
    ) -> dict[str, NarrationProfileDefinition]:
        """Return narration profiles keyed by normalized profile id."""
        return {non_blank(str(key), "narration profile id"): item for key, item in value.items()}

    @field_validator("setup_presets")
    @classmethod
    def validate_setup_presets(
        cls,
        value: dict[str, SetupPresetDefinition],
    ) -> dict[str, SetupPresetDefinition]:
        """Return setup presets keyed by normalized preset id."""
        return {non_blank(str(key), "setup preset id"): item for key, item in value.items()}


class GameDefinitions(_DefinitionModel):
    """Game-only definitions."""

    rules: GameRuleDefinitions
    roles: GameRoleDefinitions
    catalog: GameCatalogDefinitions = Field(default_factory=GameCatalogDefinitions)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Ensure references across game definition files resolve at load time."""
        role_ids = set(self.roles.roles)
        ability_ids = set(self.catalog.abilities)
        scenario_ids = set(self.catalog.scenarios)
        narration_profile_ids = set(self.catalog.narration_profiles)
        preset_ids = set(self.catalog.setup_presets)

        referenced_abilities = {
            ability_id for role in self.roles.roles.values() for ability_id in role.abilities
        }
        self._require_known(
            referenced_abilities,
            ability_ids,
            source="roles",
            target="abilities",
        )
        for scenario_id, scenario in self.catalog.scenarios.items():
            self._require_known(
                {scenario.narration_profile},
                narration_profile_ids,
                source=f"scenario {scenario_id}",
                target="narration profiles",
            )
            self._require_known(
                set(scenario.allowed_roles),
                role_ids,
                source=f"scenario {scenario_id}",
                target="roles",
            )
            if scenario.recommended_setup_preset is not None:
                self._require_known(
                    {scenario.recommended_setup_preset},
                    preset_ids,
                    source=f"scenario {scenario_id}",
                    target="setup presets",
                )
        for preset_id, preset in self.catalog.setup_presets.items():
            self._require_known(
                {preset.scenario_id},
                scenario_ids,
                source=f"setup preset {preset_id}",
                target="scenarios",
            )
            self._require_known(
                set(preset.role_counts),
                role_ids,
                source=f"setup preset {preset_id}",
                target="roles",
            )
        return self

    @staticmethod
    def _require_known(
        referenced: set[str],
        known: set[str],
        *,
        source: str,
        target: str,
    ) -> None:
        unknown = referenced - known
        if unknown:
            raise ValueError(message_definition_references_unknown_ids(source, target, unknown))


class PlayerProfile(_DefinitionModel):
    """LLM-only character persona used for names and fake decisions."""

    enabled: bool = True
    name: str
    age: int = Field(ge=MIN_CHARACTER_AGE, le=MAX_CHARACTER_AGE)
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str

    @field_validator(
        "name",
        "gender",
        "personality",
        "speaking_style",
        "reasoning_style",
        "risk_tolerance",
    )
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized profile text."""
        return non_blank(value, str(info.field_name))


class CustomCharacterDefinition(_DefinitionModel):
    """Session-scoped character definition supplied by a game API caller."""

    id: str
    name: str
    age: int = Field(ge=MIN_CHARACTER_AGE, le=MAX_CHARACTER_AGE)
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str

    @field_validator(
        "id",
        "name",
        "gender",
        "personality",
        "speaking_style",
        "reasoning_style",
        "risk_tolerance",
    )
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized custom character text."""
        return non_blank(value, str(info.field_name))


class PlayerRoster(_DefinitionModel):
    """LLM player roster definition resource."""

    players: dict[str, PlayerProfile] = Field(default_factory=dict)

    @field_validator("players")
    @classmethod
    def validate_players(cls, value: dict[str, PlayerProfile]) -> dict[str, PlayerProfile]:
        """Return enabled player profiles keyed by normalized id."""
        players = {
            non_blank(str(player_id), "player profile id"): profile
            for player_id, profile in value.items()
            if profile.enabled
        }
        if not players:
            raise ValueError(MESSAGE_PLAYERS_REQUIRED)
        names = [profile.name for profile in players.values()]
        if len(set(names)) != len(names):
            raise ValueError(MESSAGE_PLAYER_PROFILE_NAMES_MUST_BE_UNIQUE)
        return players


class AgentStrategyOption(_DefinitionModel):
    """Applicationへ公開するagent strategyの識別情報."""

    id: str
    name: str
    description: str


class PlayerSetupDefinitions(_DefinitionModel):
    """Game作成に必要なplayer profileとstrategy選択肢."""

    players: PlayerRoster
    agent_strategies: dict[str, AgentStrategyOption]

    def contains_strategy(self, strategy_id: str) -> bool:
        """Strategy IDが定義済みか返す."""
        return strategy_id in self.agent_strategies
