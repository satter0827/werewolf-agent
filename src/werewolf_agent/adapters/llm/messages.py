"""adapters llm messagesが所有する文言."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_NO_VALID_VOTE_TARGETS = "no valid vote targets"

MESSAGE_NO_ATTACK_TARGETS = "no attack targets"

MESSAGE_NO_INSPECT_TARGETS = "no inspect targets"

MESSAGE_NO_GUARD_TARGETS = "no guard targets"

MESSAGE_NO_TARGET = "no target"

MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER = "observation belongs to another player"

MESSAGE_PLAYER_IS_DEAD = "player is dead"

MESSAGE_LLM_DECISION_PLAYER_MISMATCH = "llm decision player mismatch"

MESSAGE_LLM_MODEL_NOT_CONFIGURED = "llm model is not configured"

MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE = "message is required for speech decisions"

MESSAGE_SPEECH_DECISION_FORBIDS_TARGET = "target_id is not allowed for speech decisions"

MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD = "pass decisions cannot include target_id or message"

MESSAGE_AGENT_PROFILES_REQUIRED = "profiles must include at least one enabled profile"

MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID = "prompt message role must be one of: ai, human, system"

MESSAGE_INPUT_VARIABLES_REQUIRED = "input_variables must include at least one value"

MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE = "input_variables must be unique"

MESSAGE_PROMPT_MESSAGES_REQUIRED = "messages must include at least one prompt message"

MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION = (
    "response_format.schema must be AgentModelDecision"
)


def message_field_must_be_one_of(field_name: str, choices: Iterable[str]) -> str:
    """Return a finite-choice validation message."""
    return f"{field_name} must be one of: {', '.join(sorted(choices))}"


def message_field_must_be_at_least(field_name: str, minimum: object) -> str:
    """Return a lower-bound validation message."""
    return f"{field_name} must be at least {minimum}"


def message_field_must_be_greater_than(field_name: str, minimum: object) -> str:
    """Return an exclusive lower-bound validation message."""
    return f"{field_name} must be greater than {minimum}"


def message_field_must_be_between(field_name: str, minimum: object, maximum: object) -> str:
    """Return an inclusive range validation message."""
    return f"{field_name} must be between {minimum} and {maximum}"


def message_llm_base_url_required(provider: str) -> str:
    """Return an LLM base URL requirement message."""
    return f"llm base_url is required for {provider} provider"


def message_openai_api_key_required(provider: str) -> str:
    """Return an OpenAI-compatible API key requirement message."""
    return f"OPENAI_API_KEY is required for {provider} provider"


def message_no_action_for_phase(phase: str) -> str:
    """Return an automated-agent no-action reason."""
    return f"no action for {phase}"


def message_invalid_llm_decision(error_type: str) -> str:
    """Return an invalid LLM decision parse reason."""
    return f"invalid llm decision: {error_type}"


def message_llm_decision_action_unavailable(action_type: str) -> str:
    """Return an unavailable LLM decision action reason."""
    return f"llm decision action unavailable: {action_type}"


def message_llm_decision_target_unavailable(action_type: str) -> str:
    """Return an unavailable LLM decision target reason."""
    return f"llm decision target unavailable: {action_type}"


def message_target_required(action_type: str, subject: str) -> str:
    """Return a target-required validation message."""
    return f"target_id is required for {action_type} {subject}"


def message_message_not_allowed(action_type: str, subject: str) -> str:
    """Return a message-forbidden validation message."""
    return f"message is not allowed for {action_type} {subject}"


def message_unsupported_type(value: str, subject: str) -> str:
    """Return an unsupported-type validation message."""
    return f"unsupported {subject} type: {value}"


def message_input_variables_not_used(names: str) -> str:
    """Return a prompt-template unused variable message."""
    return f"input_variables not used by messages: {names}"


def message_message_variables_missing(names: str) -> str:
    """Return a prompt-template missing variable message."""
    return f"message variables missing from input_variables: {names}"
