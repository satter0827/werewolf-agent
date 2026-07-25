"""adapters llm messagesが所有する文言."""

from __future__ import annotations

MESSAGE_NO_VALID_VOTE_TARGETS = "no valid vote targets"

MESSAGE_NO_ATTACK_TARGETS = "no attack targets"

MESSAGE_NO_INSPECT_TARGETS = "no inspect targets"

MESSAGE_NO_GUARD_TARGETS = "no guard targets"

MESSAGE_NO_TARGET = "no target"

MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER = "observation belongs to another player"

MESSAGE_PLAYER_IS_DEAD = "player is dead"

MESSAGE_LLM_DECISION_PLAYER_MISMATCH = "llm decision player mismatch"

MESSAGE_LLM_MODEL_NOT_CONFIGURED = "llm model is not configured"


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
