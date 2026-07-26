"""agents messagesが所有する文言."""

from __future__ import annotations

MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE = "message is required for speech decisions"

MESSAGE_SPEECH_DECISION_FORBIDS_TARGET = "target_id is not allowed for speech decisions"

MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD = "pass decisions cannot include target_id or message"

MESSAGE_AGENT_PROFILES_REQUIRED = "profiles must include at least one enabled profile"


def message_target_required(action_type: str, subject: str) -> str:
    """Return a target-required validation message."""
    return f"target_id is required for {action_type} {subject}"


def message_message_not_allowed(action_type: str, subject: str) -> str:
    """Return a message-forbidden validation message."""
    return f"message is not allowed for {action_type} {subject}"


def message_unsupported_type(value: str, subject: str) -> str:
    """Return an unsupported-type validation message."""
    return f"unsupported {subject} type: {value}"


MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID = "prompt message role must be one of: ai, human, system"

MESSAGE_INPUT_VARIABLES_REQUIRED = "input_variables must include at least one value"

MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE = "input_variables must be unique"

MESSAGE_PROMPT_MESSAGES_REQUIRED = "messages must include at least one prompt message"

MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION = (
    "response_format.schema must be AgentDecision"
)

MESSAGE_FAKE_DECISION_PASS_TEMPLATE_REQUIRED = "templates.pass is required"


def message_input_variables_not_used(names: str) -> str:
    """Return a prompt-template unused variable message."""
    return f"input_variables not used by messages: {names}"


def message_message_variables_missing(names: str) -> str:
    """Return a prompt-template missing variable message."""
    return f"message variables missing from input_variables: {names}"


def message_fake_decision_templates_required(action_type: str) -> str:
    """Return a FakeListLLM template coverage message."""
    return f"templates.{action_type} must include at least one item"
