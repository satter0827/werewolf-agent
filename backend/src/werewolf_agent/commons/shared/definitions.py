"""Runtime definition value models shared across layers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from string import Template
from typing import Annotated, Any, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.models import StrictModel
from werewolf_agent.commons.shared.validation import non_blank

PROMPT_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
RoleCount = Annotated[int, Field(ge=0)]


class LocalRulesDefinition(StrictModel):
    """Local rule flags used by the game core."""

    day_speech_limit_per_player: int = Field(ge=1, le=10)
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

    @model_validator(mode="after")
    def validate_tie_resolution(self) -> Self:
        """Ensure one tie-resolution behavior is active."""
        enabled = [
            self.enable_no_elimination_on_tie,
            self.enable_random_elimination_on_tie,
        ]
        if enabled.count(True) != 1:
            raise ValueError(
                "exactly one tie rule must be enabled: "
                "enable_no_elimination_on_tie, enable_random_elimination_on_tie"
            )
        return self


class AbilityDefinition(StrictModel):
    """Display and selection metadata for a supported game ability."""

    label: str
    description: str
    target_policy: str
    difficulty: int = Field(default=1, ge=1, le=5)

    @field_validator("label", "description", "target_policy")
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized ability metadata text."""
        return non_blank(value, str(info.field_name))


class RoleDefinition(StrictModel):
    """Role faction and abilities."""

    faction: str
    abilities: tuple[str, ...] = ()
    label: str | None = None
    description: str | None = None
    difficulty: int = Field(default=1, ge=1, le=5)

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
            raise ValueError("role abilities must be unique")
        return abilities


class CustomRoleDefinition(StrictModel):
    """Session-scoped role definition supplied by an interface client."""

    id: str
    name: str
    faction: str
    abilities: list[str] = Field(default_factory=list)
    description: str = ""
    difficulty: int = Field(default=1, ge=1, le=5)

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
            raise ValueError("custom role abilities must be unique")
        return abilities


class NarrationEventDefinition(StrictModel):
    """Public-safe narration templates for one event type."""

    templates: tuple[str, ...]

    @field_validator("templates")
    @classmethod
    def validate_templates(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return non-empty public narration templates."""
        templates = tuple(non_blank(item, "narration template") for item in value)
        if not templates:
            raise ValueError("narration templates must include at least one value")
        return templates


class NarrationProfileDefinition(StrictModel):
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


class ScenarioDefinition(StrictModel):
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
            raise ValueError("allowed_roles must be unique")
        return roles


class SetupPresetDefinition(StrictModel):
    """Named setup preset composed from scenario, role counts, and rules."""

    label: str
    scenario_id: str
    role_counts: dict[str, RoleCount]
    rule_profile: str = "default"

    @field_validator("label", "scenario_id", "rule_profile")
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
            raise ValueError("setup preset role_counts must include at least one player")
        return counts


class GameRuleDefinitions(StrictModel):
    """Game rule definition resource."""

    local_rules: LocalRulesDefinition


class GameRoleDefinitions(StrictModel):
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
            raise ValueError("roles must include at least one role")
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
            raise ValueError("default_role_counts must include at least one player count")
        role_ids = set(self.roles)
        for player_count, counts in self.default_role_counts.items():
            if player_count < 1:
                raise ValueError("default_role_counts keys must be positive player counts")
            unknown = sorted(set(counts) - role_ids)
            if unknown:
                raise ValueError(f"default_role_counts contain unknown roles: {', '.join(unknown)}")
            if sum(counts.values()) != player_count:
                raise ValueError(f"default_role_counts[{player_count}] must sum to {player_count}")
        return self

    def default_counts_for(self, player_count: int) -> dict[str, int]:
        """Return configured default role counts for one player count."""
        try:
            return dict(self.default_role_counts[player_count])
        except KeyError as exc:
            raise ValueError(
                f"default_role_counts must define player_count {player_count}"
            ) from exc


class GameCatalogDefinitions(StrictModel):
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


class GameDefinitions(StrictModel):
    """Game-only definitions."""

    rules: GameRuleDefinitions
    roles: GameRoleDefinitions
    catalog: GameCatalogDefinitions = Field(default_factory=GameCatalogDefinitions)


class PlayerProfile(StrictModel):
    """LLM-only character persona used for names and fake decisions."""

    enabled: bool = True
    name: str
    age: int = Field(ge=18, le=99)
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


class CustomCharacterDefinition(StrictModel):
    """Session-scoped character definition supplied by an interface client."""

    id: str
    name: str
    age: int = Field(ge=18, le=99)
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


class PlayerRoster(StrictModel):
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
            raise ValueError("players must include at least one enabled profile")
        names = [profile.name for profile in players.values()]
        if len(set(names)) != len(names):
            raise ValueError("player profile names must be unique")
        return players


class PromptMessageDefinition(StrictModel):
    """One chat message in a local prompt definition."""

    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Return a supported chat role."""
        role = non_blank(value, "prompt message role").lower()
        if role not in {"system", "human", "ai"}:
            raise ValueError("prompt message role must be one of: ai, human, system")
        return role

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Return a non-empty prompt message."""
        return non_blank(value, "prompt message content")

    def langchain_content(self) -> str:
        """Return content with MLflow-style variables converted for LangChain."""
        return PROMPT_VARIABLE_PATTERN.sub(r"{\1}", self.content)

    def variables(self) -> set[str]:
        """Return variables referenced by this message."""
        return set(PROMPT_VARIABLE_PATTERN.findall(self.content))


class PromptDefinition(StrictModel):
    """MLflow-compatible local prompt definition."""

    name: str
    version: int = Field(ge=1)
    alias: str
    input_variables: list[str]
    tags: dict[str, str] = Field(default_factory=dict)
    model_config_metadata: dict[str, object] = Field(
        default_factory=dict,
        alias="model_config",
    )
    response_format: dict[str, str]
    messages: list[PromptMessageDefinition]

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @field_validator("name", "alias")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Return normalized prompt metadata text."""
        return non_blank(value, "prompt metadata")

    @field_validator("input_variables")
    @classmethod
    def validate_input_variables(cls, value: list[str]) -> list[str]:
        """Return unique non-empty input variable names."""
        variables = [non_blank(item, "input variable") for item in value]
        if not variables:
            raise ValueError("input_variables must include at least one value")
        if len(set(variables)) != len(variables):
            raise ValueError("input_variables must be unique")
        return variables

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: dict[str, str]) -> dict[str, str]:
        """Return prompt tags with non-empty keys and values."""
        return {
            non_blank(key, "prompt tag key"): non_blank(item, "prompt tag value")
            for key, item in value.items()
        }

    @field_validator("response_format")
    @classmethod
    def validate_response_format(cls, value: dict[str, str]) -> dict[str, str]:
        """Return response format metadata with non-empty keys and values."""
        return {
            non_blank(key, "response format key"): non_blank(item, "response format value")
            for key, item in value.items()
        }

    @model_validator(mode="after")
    def validate_prompt_contract(self) -> Self:
        """Ensure the prompt template and output schema agree."""
        if not self.messages:
            raise ValueError("messages must include at least one prompt message")
        if self.response_format.get("schema") != "AgentDecision":
            raise ValueError("response_format.schema must be AgentDecision")
        expected = set(self.input_variables)
        actual = set().union(*(message.variables() for message in self.messages))
        missing_from_messages = expected - actual
        missing_from_metadata = actual - expected
        if missing_from_messages:
            names = ", ".join(sorted(missing_from_messages))
            raise ValueError(f"input_variables not used by messages: {names}")
        if missing_from_metadata:
            names = ", ".join(sorted(missing_from_metadata))
            raise ValueError(f"message variables missing from input_variables: {names}")
        return self


class FakeDecisionTemplate(StrictModel):
    """One local FakeListLLM response template."""

    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Return a non-empty fake decision template."""
        return non_blank(value, "fake decision template")

    def render(self, context: Mapping[str, object]) -> str:
        """Render this template with a simple standard-library placeholder engine."""
        values = {key: str(value) for key, value in context.items()}
        return Template(self.content).safe_substitute(values).strip()


class FakeDecisionCatalog(StrictModel):
    """Local FakeListLLM response catalog."""

    name: str
    version: int = Field(ge=1)
    alias: str
    tags: dict[str, str] = Field(default_factory=dict)
    templates: dict[str, tuple[FakeDecisionTemplate, ...]]

    @field_validator("name", "alias")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Return normalized fake response metadata text."""
        return non_blank(value, "fake decision metadata")

    @field_validator("templates", mode="before")
    @classmethod
    def normalize_template_keys(cls, value: object) -> object:
        """Return templates keyed by action type id."""
        if not isinstance(value, Mapping):
            return value
        normalized: dict[str, object] = {}
        for key, item in value.items():
            action_type = non_blank(str(key), "fake decision action type")
            raw_items = item if isinstance(item, list) else [item]
            normalized[action_type] = [
                {"content": raw_item} if isinstance(raw_item, str) else raw_item
                for raw_item in raw_items
            ]
        return normalized

    @field_validator("templates")
    @classmethod
    def validate_templates(
        cls,
        value: dict[str, tuple[FakeDecisionTemplate, ...]],
    ) -> dict[str, tuple[FakeDecisionTemplate, ...]]:
        """Return non-empty fake decision templates."""
        if "pass" not in value:
            raise ValueError("templates.pass is required")
        templates = {}
        for key, items in value.items():
            action_type = non_blank(key, "fake decision action type")
            if not items:
                raise ValueError(f"templates.{action_type} must include at least one item")
            templates[action_type] = tuple(items)
        return templates

    def render(
        self,
        action_type: str,
        *,
        context: Mapping[str, object],
        selector: int = 0,
    ) -> str:
        """Return one rendered JSON response."""
        template_pool = self.templates.get(action_type) or self.templates["pass"]
        template = template_pool[selector % len(template_pool)]
        return template.render(context)


class LlmDefinitions(StrictModel):
    """LLM-only definitions."""

    players: PlayerRoster
    prompt: PromptDefinition
    fake_responses: FakeDecisionCatalog


__all__ = [
    "AbilityDefinition",
    "CustomCharacterDefinition",
    "CustomRoleDefinition",
    "FakeDecisionCatalog",
    "FakeDecisionTemplate",
    "GameCatalogDefinitions",
    "GameDefinitions",
    "GameRoleDefinitions",
    "GameRuleDefinitions",
    "LlmDefinitions",
    "LocalRulesDefinition",
    "NarrationEventDefinition",
    "NarrationProfileDefinition",
    "PlayerProfile",
    "PlayerRoster",
    "PromptDefinition",
    "PromptMessageDefinition",
    "RoleDefinition",
    "ScenarioDefinition",
    "SetupPresetDefinition",
]
