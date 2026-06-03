"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from werewolf_agent.commons.shared.definitions import FakeDecisionCatalog, PromptDefinition
from werewolf_agent.commons.shared.messages import (
    MESSAGE_LLM_DECISION_PLAYER_MISMATCH,
    MESSAGE_LLM_MODEL_NOT_CONFIGURED,
    MESSAGE_NO_ATTACK_TARGETS,
    MESSAGE_NO_GUARD_TARGETS,
    MESSAGE_NO_INSPECT_TARGETS,
    MESSAGE_NO_TARGET,
    MESSAGE_NO_VALID_VOTE_TARGETS,
    MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
    MESSAGE_PLAYER_IS_DEAD,
    message_invalid_llm_decision,
    message_llm_decision_action_unavailable,
    message_llm_decision_target_unavailable,
    message_no_action_for_phase,
)
from werewolf_agent.domain.llm.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    VisiblePlayer,
)


@dataclass(frozen=True)
class LangChainDecisionProvider:
    """Decision provider that renders a prompt and parses LangChain model output."""

    prompt: PromptDefinition
    model: Any | None = None
    fake_responses: FakeDecisionCatalog | None = None
    parser: PydanticOutputParser[AgentDecision] = field(
        default_factory=lambda: PydanticOutputParser(pydantic_object=AgentDecision)
    )

    def choose_decision(self, player_id: str, observation: AgentObservation) -> AgentDecision:
        """Return one validated decision from visible player context."""
        preflight_decision = _preflight_decision(player_id, observation)
        if preflight_decision is not None:
            return preflight_decision

        observation = observation.model_copy(
            update={"legal_targets": _legal_targets_by_action(observation)}
        )
        action_type = _selected_action(observation)
        target_id = _target_for_action(observation, action_type)
        if action_type in AgentDecision.TARGET_TYPES and target_id is None:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=_missing_target_reason(action_type),
            )

        prompt_value = _to_chat_prompt(self.prompt).invoke(
            _prompt_inputs(
                player_id,
                observation,
                parser=self.parser,
            )
        )
        try:
            raw_output = self._invoke_model(
                prompt_value,
                action_type,
                player_id,
                target_id,
                observation,
            )
            decision = self.parser.parse(_output_text(raw_output))
        except Exception as exc:
            return AgentDecision.pass_(
                player_id=player_id,
                reason=message_invalid_llm_decision(type(exc).__name__),
            )
        return _validated_decision(player_id, observation, decision)

    def _invoke_model(
        self,
        prompt_value: Any,
        action_type: AgentActionType,
        player_id: str,
        target_id: str | None,
        observation: AgentObservation,
    ) -> object:
        if self.fake_responses is not None:
            response = self.fake_responses.render(
                action_type.value,
                context=_fake_template_context(player_id, target_id, observation),
                selector=_fake_response_selector(player_id, action_type, target_id, observation),
            )
            return FakeListLLM(responses=[response]).invoke(prompt_value)
        if self.model is None:
            raise RuntimeError(MESSAGE_LLM_MODEL_NOT_CONFIGURED)
        return self.model.invoke(prompt_value)


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


def _to_chat_prompt(prompt: PromptDefinition) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [(message.role, message.langchain_content()) for message in prompt.messages]
    )


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
    candidates = _legal_targets_by_action(observation).get(action_type, [])
    if not candidates:
        return None
    selector = _fake_target_selector(observation.me.id, observation, action_type)
    return candidates[selector % len(candidates)]


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
        attacker_role = observation.role
        return [
            player_id
            for player_id in alive_players
            if player_id != observation.me.id
            and (attacker_role is None or observation.known_roles.get(player_id) != attacker_role)
        ]
    if action_type is AgentActionType.KNIGHT_GUARD:
        return alive_players
    return []


def _legal_targets_by_action(
    observation: AgentObservation,
) -> dict[AgentActionType, list[str]]:
    """Return legal target ids for available target-taking actions."""
    targets: dict[AgentActionType, list[str]] = {}
    for action_type in observation.available_actions:
        if action_type not in AgentDecision.TARGET_TYPES:
            continue
        configured_targets = observation.legal_targets.get(action_type)
        targets[action_type] = (
            list(configured_targets)
            if configured_targets is not None
            else _target_candidates(observation, action_type)
        )
    return targets


def _missing_target_reason(action_type: AgentActionType) -> str:
    if action_type is AgentActionType.VOTE:
        return MESSAGE_NO_VALID_VOTE_TARGETS
    if action_type is AgentActionType.WEREWOLF_ATTACK:
        return MESSAGE_NO_ATTACK_TARGETS
    if action_type is AgentActionType.SEER_INSPECT:
        return MESSAGE_NO_INSPECT_TARGETS
    if action_type is AgentActionType.KNIGHT_GUARD:
        return MESSAGE_NO_GUARD_TARGETS
    return MESSAGE_NO_TARGET


def _fake_response_selector(
    player_id: str,
    action_type: AgentActionType,
    target_id: str | None,
    observation: AgentObservation,
) -> int:
    digest = sha256(
        (
            f"{player_id}:{action_type.value}:{target_id or ''}:"
            f"{observation.day}:{len(observation.speeches)}:{len(observation.vote_rounds)}"
        ).encode()
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _fake_target_selector(
    player_id: str,
    observation: AgentObservation,
    action_type: AgentActionType,
) -> int:
    digest = sha256(f"{player_id}:{action_type.value}:{observation.day}:target".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _fake_template_context(
    player_id: str,
    target_id: str | None,
    observation: AgentObservation,
) -> dict[str, str]:
    target = next((player for player in observation.players if player.id == target_id), None)
    focus = _focus_player(observation)
    profile = observation.profile
    return {
        "player_id": player_id,
        "player_name": observation.me.name,
        "target_id": target_id or "",
        "target_name": target.name if target is not None else "",
        "focus_id": focus.id if focus is not None else "",
        "focus_name": focus.name if focus is not None else "",
        "day": str(observation.day),
        "phase": observation.phase.value,
        "role": observation.role or "",
        "persona": _persona_text(profile),
        "character_profile": _character_profile_text(profile),
        "scenario_name": observation.scenario.name if observation.scenario is not None else "",
        "scenario_premise": (
            observation.scenario.premise if observation.scenario is not None else ""
        ),
        "profile_name": profile.name if profile is not None else observation.me.name,
    }


def _persona_text(profile: object | None) -> str:
    if profile is None:
        return ""
    personality = getattr(profile, "personality", "")
    speaking_style = getattr(profile, "speaking_style", "")
    reasoning_style = getattr(profile, "reasoning_style", "")
    risk_tolerance = getattr(profile, "risk_tolerance", "")
    return " / ".join(
        item
        for item in [personality, speaking_style, reasoning_style, f"risk={risk_tolerance}"]
        if item
    )


def _character_profile_text(profile: object | None) -> str:
    if profile is None:
        return ""
    name = getattr(profile, "name", "")
    age = getattr(profile, "age", "")
    gender = getattr(profile, "gender", "")
    personality = getattr(profile, "personality", "")
    speaking_style = getattr(profile, "speaking_style", "")
    reasoning_style = getattr(profile, "reasoning_style", "")
    risk_tolerance = getattr(profile, "risk_tolerance", "")
    return " / ".join(
        str(item)
        for item in [
            f"name={name}" if name else "",
            f"age={age}" if age else "",
            f"gender={gender}" if gender else "",
            f"personality={personality}" if personality else "",
            f"speaking_style={speaking_style}" if speaking_style else "",
            f"reasoning_style={reasoning_style}" if reasoning_style else "",
            f"risk={risk_tolerance}" if risk_tolerance else "",
        ]
        if item
    )


def _focus_player(observation: AgentObservation) -> VisiblePlayer | None:
    candidates = [
        player
        for player in observation.players
        if player.status is AgentPlayerStatus.ALIVE and player.id != observation.me.id
    ]
    if not candidates:
        return None
    selector = _fake_target_selector(
        observation.me.id,
        observation,
        AgentActionType.SPEECH,
    )
    return candidates[selector % len(candidates)]


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
        "role": observation.role if observation.role is not None else "",
        "scenario_name": observation.scenario.name if observation.scenario is not None else "",
        "scenario_premise": (
            observation.scenario.premise if observation.scenario is not None else ""
        ),
        "character_profile": _character_profile_text(observation.profile),
        "available_actions": json.dumps(
            [action.value for action in observation.available_actions],
            ensure_ascii=False,
        ),
        "legal_targets_json": json.dumps(
            {
                action_type.value: player_ids
                for action_type, player_ids in _legal_targets_by_action(observation).items()
            },
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
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_LLM_DECISION_PLAYER_MISMATCH)
    if decision.type is AgentActionType.PASS:
        return decision
    if decision.type not in observation.available_actions:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_llm_decision_action_unavailable(decision.type.value),
        )
    if (
        decision.type in AgentDecision.TARGET_TYPES
        and decision.target_id not in _legal_targets_by_action(observation).get(decision.type, [])
    ):
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_llm_decision_target_unavailable(decision.type.value),
        )
    return decision


__all__ = [
    "LangChainDecisionProvider",
]
