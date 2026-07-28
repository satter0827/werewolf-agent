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
