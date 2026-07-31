"""agents definition models."""

from __future__ import annotations

import re
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.adapters.llm.constants import (
    MAX_CHARACTER_AGE,
    MIN_CHARACTER_AGE,
    MIN_VERSION,
)
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE,
    MESSAGE_INPUT_VARIABLES_REQUIRED,
    MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID,
    MESSAGE_PROMPT_MESSAGES_REQUIRED,
    MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION,
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
    evidence_focus: str = "vote_consistency"

    @field_validator(
        "name",
        "gender",
        "personality",
        "speaking_style",
        "reasoning_style",
        "risk_tolerance",
        "evidence_focus",
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


class DeliberationSettings(_DefinitionModel):
    """Resource-owned context and output limits for one deliberation level."""

    event_limit: int = Field(ge=1)
    output_token_limit: int = Field(ge=1)


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
    deliberation: dict[str, DeliberationSettings]
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

    @model_validator(mode="after")
    def validate_prompt_contract(self) -> Self:
        """Ensure the prompt template and output schema agree."""
        if not self.messages:
            raise ValueError(MESSAGE_PROMPT_MESSAGES_REQUIRED)
        if self.response_format.get("schema") != "AgentModelDecision":
            raise ValueError(MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION)
        if set(self.deliberation) != {"quick", "standard", "deep"}:
            raise ValueError("deliberation must define quick, standard, and deep")
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
