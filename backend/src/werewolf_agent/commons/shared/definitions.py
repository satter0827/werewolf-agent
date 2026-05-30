"""Runtime definition value models shared across layers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.models import StrictModel
from werewolf_agent.commons.shared.validation import non_blank

PROMPT_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
RoleCount = Annotated[int, Field(ge=0)]


class LocalRulesDefinition(StrictModel):
    """Local rule flags used by the game core."""

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


class RoleDefinition(StrictModel):
    """Role faction and abilities."""

    faction: str
    abilities: tuple[str, ...] = ()

    @field_validator("faction")
    @classmethod
    def validate_faction(cls, value: str) -> str:
        """Return a normalized faction id."""
        return non_blank(value, "faction")

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return normalized unique ability ids."""
        abilities = tuple(non_blank(item, "ability") for item in value)
        if len(set(abilities)) != len(abilities):
            raise ValueError("role abilities must be unique")
        return abilities


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


class GameDefinitions(StrictModel):
    """Game-only definitions."""

    rules: GameRuleDefinitions
    roles: GameRoleDefinitions


class AgentDefinition(StrictModel):
    """LLM-only agent behavior profile."""

    enabled: bool = True
    name: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str

    @field_validator(
        "name",
        "personality",
        "speaking_style",
        "reasoning_style",
        "risk_tolerance",
    )
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized profile text."""
        return non_blank(value, str(info.field_name))


class LlmAgentDefinitions(StrictModel):
    """LLM agent profile definition resource."""

    agents: dict[str, AgentDefinition] = Field(default_factory=dict)

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, value: dict[str, AgentDefinition]) -> dict[str, AgentDefinition]:
        """Return enabled agent profiles keyed by normalized id."""
        agents = {
            non_blank(str(agent_id), "agent id"): profile
            for agent_id, profile in value.items()
            if profile.enabled
        }
        if not agents:
            raise ValueError("agents must include at least one enabled profile")
        return agents


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


class FakeResponsesDefinition(StrictModel):
    """Local fake response fixtures."""

    name: str
    version: int = Field(ge=1)
    alias: str
    tags: dict[str, str] = Field(default_factory=dict)
    responses: dict[str, tuple[str, ...]]

    @field_validator("name", "alias")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Return normalized fake response metadata text."""
        return non_blank(value, "fake response metadata")

    @field_validator("responses", mode="before")
    @classmethod
    def normalize_response_keys(cls, value: object) -> object:
        """Return responses keyed by action type id."""
        if not isinstance(value, Mapping):
            return value
        normalized: dict[str, object] = {}
        for key, item in value.items():
            action_type = non_blank(str(key), "fake response action type")
            normalized[action_type] = item if isinstance(item, list) else [item]
        return normalized

    @field_validator("responses")
    @classmethod
    def validate_responses(
        cls,
        value: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        """Return non-empty fake response templates."""
        if "pass" not in value:
            raise ValueError("responses.pass is required")
        return {
            non_blank(key, "fake response action type"): tuple(
                non_blank(item, f"fake response {key}") for item in items
            )
            for key, items in value.items()
        }

    def response_for(
        self,
        action_type: str,
        *,
        player_id: str,
        target_id: str | None,
        selector: int = 0,
    ) -> str:
        """Return one JSON response with placeholders filled."""
        response_pool = self.responses.get(action_type) or self.responses["pass"]
        template = response_pool[selector % len(response_pool)]
        return (
            template.replace("{{player_id}}", player_id)
            .replace("{{target_id}}", target_id or "")
            .strip()
        )


class LlmDefinitions(StrictModel):
    """LLM-only definitions."""

    agents: LlmAgentDefinitions
    prompt: PromptDefinition
    fake_responses: FakeResponsesDefinition


__all__ = [
    "AgentDefinition",
    "FakeResponsesDefinition",
    "GameDefinitions",
    "GameRoleDefinitions",
    "GameRuleDefinitions",
    "LlmAgentDefinitions",
    "LlmDefinitions",
    "LocalRulesDefinition",
    "PromptDefinition",
    "PromptMessageDefinition",
    "RoleDefinition",
]
