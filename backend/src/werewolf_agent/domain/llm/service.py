"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.messages import (
    MESSAGE_NO_ATTACK_TARGETS,
    MESSAGE_NO_GUARD_TARGETS,
    MESSAGE_NO_INSPECT_TARGETS,
    MESSAGE_NO_VALID_VOTE_TARGETS,
    MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
    MESSAGE_PLAYER_IS_DEAD,
    message_no_action_for_phase,
)
from werewolf_agent.commons.shared.validation import non_blank
from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    AgentRole,
)

PROMPTS_PACKAGE: Final = "werewolf_agent.resources.prompts"
PROMPT_FILE: Final = "agent_decision.toml"
FAKE_RESPONSES_PACKAGE: Final = "werewolf_agent.resources.llm"
FAKE_RESPONSES_FILE: Final = "fake_responses.toml"
PROMPT_VARIABLE_PATTERN: Final = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


class PromptMessage(BaseModel):
    """One chat message in a local MLflow-compatible prompt resource."""

    role: str
    content: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Return a supported LangChain chat role."""
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
        """Return MLflow-style variables referenced by this message."""
        return set(PROMPT_VARIABLE_PATTERN.findall(self.content))


class PromptResource(BaseModel):
    """MLflow-compatible local prompt metadata and chat template."""

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
    messages: list[PromptMessage]

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @field_validator("name", "alias")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Return stripped prompt metadata text."""
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
        """Return prompt tags with non-empty string keys and values."""
        return {
            non_blank(key, "prompt tag key"): non_blank(item, "prompt tag value")
            for key, item in value.items()
        }

    @field_validator("response_format")
    @classmethod
    def validate_response_format(cls, value: dict[str, str]) -> dict[str, str]:
        """Return response format metadata with non-empty string keys and values."""
        return {
            non_blank(key, "response format key"): non_blank(item, "response format value")
            for key, item in value.items()
        }

    @model_validator(mode="after")
    def validate_prompt_contract(self) -> PromptResource:
        """Ensure the prompt template and output schema agree with the code contract."""
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

    def to_chat_prompt(self) -> ChatPromptTemplate:
        """Return a LangChain chat prompt for this local prompt resource."""
        return ChatPromptTemplate.from_messages(
            [(message.role, message.langchain_content()) for message in self.messages]
        )


class FakeResponseResource(BaseModel):
    """MLflow-compatible local fake response fixtures for LangChain FakeListLLM."""

    name: str
    version: int = Field(ge=1)
    alias: str
    tags: dict[str, str] = Field(default_factory=dict)
    responses: dict[AgentActionType, tuple[str, ...]]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("name", "alias")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Return stripped fake response metadata text."""
        return non_blank(value, "fake response metadata")

    @field_validator("responses", mode="before")
    @classmethod
    def normalize_response_keys(cls, value: object) -> object:
        """Return responses keyed by structured action type."""
        if not isinstance(value, Mapping):
            return value
        normalized: dict[AgentActionType, object] = {}
        for key, item in value.items():
            action_type = AgentActionType(str(key))
            normalized[action_type] = item if isinstance(item, list) else [item]
        return normalized

    @field_validator("responses")
    @classmethod
    def validate_responses(
        cls,
        value: dict[AgentActionType, tuple[str, ...]],
    ) -> dict[AgentActionType, tuple[str, ...]]:
        """Return non-empty fake response templates."""
        if AgentActionType.PASS not in value:
            raise ValueError("responses.pass is required")
        return {
            key: tuple(non_blank(item, f"fake response {key.value}") for item in items)
            for key, items in value.items()
        }

    def response_for(
        self,
        action_type: AgentActionType,
        *,
        player_id: str,
        target_id: str | None,
        selector: int = 0,
    ) -> str:
        """Return one JSON response with MLflow-style placeholders filled."""
        response_pool = self.responses.get(action_type) or self.responses[AgentActionType.PASS]
        template = response_pool[selector % len(response_pool)]
        return (
            template.replace("{{player_id}}", player_id)
            .replace("{{target_id}}", target_id or "")
            .strip()
        )


@dataclass(frozen=True)
class LangChainDecisionProvider:
    """Decision provider that renders a prompt and parses LangChain model output."""

    prompt: PromptResource
    model: Any | None = None
    fake_responses: FakeResponseResource | None = None
    parser: PydanticOutputParser[AgentDecision] = field(
        default_factory=lambda: PydanticOutputParser(pydantic_object=AgentDecision)
    )

    def choose_decision(self, player_id: str, observation: AgentObservation) -> AgentDecision:
        """Return one validated decision from visible player context."""
        preflight_decision = _preflight_decision(player_id, observation)
        if preflight_decision is not None:
            return preflight_decision

        action_type = _selected_action(observation)
        target_id = _target_for_action(observation, action_type)
        if action_type in AgentDecision.TARGET_TYPES and target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action_type),
            )

        prompt_value = self.prompt.to_chat_prompt().invoke(
            _prompt_inputs(
                player_id,
                observation,
                parser=self.parser,
            )
        )
        try:
            raw_output = self._invoke_model(prompt_value, action_type, player_id, target_id)
            decision = self.parser.parse(_output_text(raw_output))
        except Exception as exc:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=f"invalid llm decision: {type(exc).__name__}",
            )
        return _validated_decision(player_id, observation, decision)

    def _invoke_model(
        self,
        prompt_value: Any,
        action_type: AgentActionType,
        player_id: str,
        target_id: str | None,
    ) -> object:
        if self.fake_responses is not None:
            response = self.fake_responses.response_for(
                action_type,
                player_id=player_id,
                target_id=target_id,
                selector=_fake_response_selector(player_id, action_type, target_id),
            )
            return FakeListLLM(responses=[response]).invoke(prompt_value)
        if self.model is None:
            raise RuntimeError("llm model is not configured")
        return self.model.invoke(prompt_value)


def load_prompt_resource(path: Path | None = None) -> PromptResource:
    """Load one MLflow-compatible local prompt resource."""
    if path is None:
        with files(PROMPTS_PACKAGE).joinpath(PROMPT_FILE).open("rb") as prompt_file:
            return PromptResource.model_validate(tomllib.load(prompt_file))
    with path.open("rb") as prompt_file:
        return PromptResource.model_validate(tomllib.load(prompt_file))


def load_fake_response_resource(path: Path | None = None) -> FakeResponseResource:
    """Load local fake response fixtures for LangChain FakeListLLM."""
    if path is None:
        with (
            files(FAKE_RESPONSES_PACKAGE).joinpath(FAKE_RESPONSES_FILE).open("rb") as response_file
        ):
            return FakeResponseResource.model_validate(tomllib.load(response_file))
    with path.open("rb") as response_file:
        return FakeResponseResource.model_validate(tomllib.load(response_file))


def build_fake_decision_provider(
    *,
    prompt_path: Path | None = None,
    fake_responses_path: Path | None = None,
) -> LangChainDecisionProvider:
    """Return a LangChain provider backed by FakeListLLM fixtures."""
    return LangChainDecisionProvider(
        prompt=load_prompt_resource(prompt_path),
        fake_responses=load_fake_response_resource(fake_responses_path),
    )


def _preflight_decision(
    player_id: str,
    observation: AgentObservation,
) -> AgentDecision | None:
    if observation.me.id != player_id:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
        )
    if observation.me.status is not AgentPlayerStatus.ALIVE:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_PLAYER_IS_DEAD)
    if not observation.available_actions:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_no_action_for_phase(observation.phase.value),
        )
    return None


def _selected_action(observation: AgentObservation) -> AgentActionType:
    if observation.phase is AgentPhase.DAY_DISCUSSION:
        return _first_available(observation, AgentActionType.SPEECH)
    if observation.phase is AgentPhase.VOTING:
        return _first_available(observation, AgentActionType.VOTE)
    if observation.phase is AgentPhase.NIGHT:
        for action_type in (
            AgentActionType.WEREWOLF_ATTACK,
            AgentActionType.SEER_INSPECT,
            AgentActionType.KNIGHT_GUARD,
        ):
            if action_type in observation.available_actions:
                return action_type
    return AgentActionType.PASS


def _first_available(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> AgentActionType:
    return action_type if action_type in observation.available_actions else AgentActionType.PASS


def _target_for_action(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> str | None:
    candidates = _target_candidates(observation, action_type)
    return candidates[0] if candidates else None


def _target_candidates(
    observation: AgentObservation,
    action_type: AgentActionType,
) -> list[str]:
    alive_players = [
        player.id for player in observation.players if player.status is AgentPlayerStatus.ALIVE
    ]
    if action_type in {AgentActionType.VOTE, AgentActionType.SEER_INSPECT}:
        return [player_id for player_id in alive_players if player_id != observation.me.id]
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return [
            player_id
            for player_id in alive_players
            if player_id != observation.me.id
            and observation.known_roles.get(player_id) is not AgentRole.WEREWOLF
        ]
    if action_type is AgentActionType.KNIGHT_GUARD:
        return alive_players
    return []


def _missing_target_reason(action_type: AgentActionType) -> str:
    if action_type is AgentActionType.VOTE:
        return MESSAGE_NO_VALID_VOTE_TARGETS
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return MESSAGE_NO_ATTACK_TARGETS
    if action_type is AgentActionType.SEER_INSPECT:
        return MESSAGE_NO_INSPECT_TARGETS
    if action_type is AgentActionType.KNIGHT_GUARD:
        return MESSAGE_NO_GUARD_TARGETS
    return "no target"


def _fake_response_selector(
    player_id: str,
    action_type: AgentActionType,
    target_id: str | None,
) -> int:
    digest = sha256(f"{player_id}:{action_type.value}:{target_id or ''}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _prompt_inputs(
    player_id: str,
    observation: AgentObservation,
    *,
    parser: PydanticOutputParser[AgentDecision],
) -> dict[str, str]:
    return {
        "player_id": player_id,
        "phase": observation.phase.value,
        "day": str(observation.day),
        "role": observation.role.value if observation.role is not None else "",
        "available_actions": json.dumps(
            [action.value for action in observation.available_actions],
            ensure_ascii=False,
        ),
        "observation_json": observation.model_dump_json(),
        "format_instructions": parser.get_format_instructions(),
    }


def _output_text(raw_output: object) -> str:
    if isinstance(raw_output, str):
        return raw_output
    content = getattr(raw_output, "content", None)
    if isinstance(content, str):
        return content
    return str(raw_output)


def _validated_decision(
    player_id: str,
    observation: AgentObservation,
    decision: AgentDecision,
) -> AgentDecision:
    if decision.player_id != player_id:
        return AgentDecision.pass_(player_id=player_id, reason="llm decision player mismatch")
    if decision.type is AgentActionType.PASS:
        return decision
    if decision.type not in observation.available_actions:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=f"llm decision action unavailable: {decision.type.value}",
        )
    if decision.type in AgentDecision.TARGET_TYPES and decision.target_id not in _target_candidates(
        observation, decision.type
    ):
        return AgentDecision.pass_(
            player_id=player_id,
            reason=f"llm decision target unavailable: {decision.type.value}",
        )
    return decision


__all__ = [
    "FakeResponseResource",
    "LangChainDecisionProvider",
    "PromptMessage",
    "PromptResource",
    "build_fake_decision_provider",
    "load_fake_response_resource",
    "load_prompt_resource",
]
