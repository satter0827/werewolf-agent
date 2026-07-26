"""agents definition models."""

from __future__ import annotations

import re
from collections.abc import Mapping
from string import Template
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.agents.constants import MAX_CHARACTER_AGE, MIN_CHARACTER_AGE, MIN_VERSION
from werewolf_agent.agents.messages import (
    MESSAGE_FAKE_DECISION_PASS_TEMPLATE_REQUIRED,
    MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE,
    MESSAGE_INPUT_VARIABLES_REQUIRED,
    MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID,
    MESSAGE_PROMPT_MESSAGES_REQUIRED,
    MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION,
    message_fake_decision_templates_required,
    message_input_variables_not_used,
    message_message_variables_missing,
)
from werewolf_agent.agents.validation import non_blank

PROMPT_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


class _DefinitionModel(BaseModel):
    """Base model for immutable agent definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)


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


class PromptMessageDefinition(_DefinitionModel):
    """One chat message in a local prompt definition."""

    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Return a supported chat role."""
        role = non_blank(value, "prompt message role").lower()
        if role not in {"system", "human", "ai"}:
            raise ValueError(MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID)
        return role

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Return a non-empty prompt message."""
        return non_blank(value, "prompt message content")

    def variables(self) -> set[str]:
        """Return variables referenced by this message."""
        return set(PROMPT_VARIABLE_PATTERN.findall(self.content))


class PromptDefinition(_DefinitionModel):
    """MLflow-compatible local prompt definition."""

    name: str
    version: int = Field(ge=MIN_VERSION)
    alias: str
    input_variables: list[str]
    tags: dict[str, str] = Field(default_factory=dict)
    model_config_metadata: dict[str, object] = Field(
        default_factory=dict,
        alias="model_config",
    )
    response_format: dict[str, str]
    role_hints: dict[str, str] = Field(default_factory=dict)
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
            raise ValueError(MESSAGE_INPUT_VARIABLES_REQUIRED)
        if len(set(variables)) != len(variables):
            raise ValueError(MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE)
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

    @field_validator("role_hints")
    @classmethod
    def validate_role_hints(cls, value: dict[str, str]) -> dict[str, str]:
        """Return role guidance keyed by normalized role id."""
        return {
            non_blank(str(role_id), "role hint id"): non_blank(hint, "role hint")
            for role_id, hint in value.items()
        }

    @model_validator(mode="after")
    def validate_prompt_contract(self) -> Self:
        """Ensure the prompt template and output schema agree."""
        if not self.messages:
            raise ValueError(MESSAGE_PROMPT_MESSAGES_REQUIRED)
        if self.response_format.get("schema") != "AgentDecision":
            raise ValueError(MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION)
        expected = set(self.input_variables)
        actual = set().union(*(message.variables() for message in self.messages))
        missing_from_messages = expected - actual
        missing_from_metadata = actual - expected
        if missing_from_messages:
            names = ", ".join(sorted(missing_from_messages))
            raise ValueError(message_input_variables_not_used(names))
        if missing_from_metadata:
            names = ", ".join(sorted(missing_from_metadata))
            raise ValueError(message_message_variables_missing(names))
        return self


class FakeDecisionTemplate(_DefinitionModel):
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


class FakeDecisionCatalog(_DefinitionModel):
    """Local FakeListLLM response catalog."""

    name: str
    version: int = Field(ge=MIN_VERSION)
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
            raise ValueError(MESSAGE_FAKE_DECISION_PASS_TEMPLATE_REQUIRED)
        templates = {}
        for key, items in value.items():
            action_type = non_blank(key, "fake decision action type")
            if not items:
                raise ValueError(message_fake_decision_templates_required(action_type))
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
