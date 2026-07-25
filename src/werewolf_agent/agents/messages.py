"""agents messagesが所有する文言."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_SPEECH_DECISION_REQUIRES_MESSAGE = "message is required for speech decisions"

MESSAGE_SPEECH_DECISION_FORBIDS_TARGET = "target_id is not allowed for speech decisions"

MESSAGE_PASS_DECISION_FORBIDS_PAYLOAD = "pass decisions cannot include target_id or message"

MESSAGE_AGENT_PROFILES_REQUIRED = "profiles must include at least one enabled profile"


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


def message_target_required(action_type: str, subject: str) -> str:
    """Return a target-required validation message."""
    return f"target_id is required for {action_type} {subject}"


def message_message_not_allowed(action_type: str, subject: str) -> str:
    """Return a message-forbidden validation message."""
    return f"message is not allowed for {action_type} {subject}"


def message_unsupported_type(value: str, subject: str) -> str:
    """Return an unsupported-type validation message."""
    return f"unsupported {subject} type: {value}"


def message_llm_base_url_required(provider: str) -> str:
    """Return an LLM base URL requirement message."""
    return f"llm base_url is required for {provider} provider"


def message_openai_api_key_required(provider: str) -> str:
    """Return an OpenAI-compatible API key requirement message."""
    return f"OPENAI_API_KEY is required for {provider} provider"


MESSAGE_PROMPT_MESSAGE_ROLE_MUST_BE_VALID = "prompt message role must be one of: ai, human, system"

MESSAGE_INPUT_VARIABLES_REQUIRED = "input_variables must include at least one value"

MESSAGE_INPUT_VARIABLES_MUST_BE_UNIQUE = "input_variables must be unique"

MESSAGE_PROMPT_MESSAGES_REQUIRED = "messages must include at least one prompt message"

MESSAGE_RESPONSE_FORMAT_SCHEMA_MUST_BE_AGENT_DECISION = (
    "response_format.schema must be AgentDecision"
)

MESSAGE_FAKE_DECISION_PASS_TEMPLATE_REQUIRED = "templates.pass is required"

MESSAGE_AGENT_STRATEGIES_REQUIRED = "agent strategies must include at least one strategy"

MESSAGE_AGENT_STRATEGY_IDS_MUST_BE_UNIQUE = "agent strategy ids must be unique"

MESSAGE_AGENT_STRATEGY_DEFAULT_EXACTLY_ONE = (
    "agent strategies must mark exactly one default strategy"
)

MESSAGE_AGENT_STRATEGY_NODES_REQUIRED = "agent strategy nodes must include at least one node"

MESSAGE_AGENT_STRATEGY_NODES_MUST_BE_UNIQUE = "agent strategy nodes must be unique"

MESSAGE_DECISION_GRAPH_EDGES_REQUIRED = "decision graph edges must include at least one edge"

MESSAGE_DECISION_GRAPH_ROUTES_MUST_BE_UNIQUE = "decision graph routes must be unique"


def message_input_variables_not_used(names: str) -> str:
    """Return a prompt-template unused variable message."""
    return f"input_variables not used by messages: {names}"


def message_message_variables_missing(names: str) -> str:
    """Return a prompt-template missing variable message."""
    return f"message variables missing from input_variables: {names}"


def message_fake_decision_templates_required(action_type: str) -> str:
    """Return a FakeListLLM template coverage message."""
    return f"templates.{action_type} must include at least one item"


def message_decision_graph_node_unknown(node_id: str) -> str:
    """Return an unknown registered decision-graph node message."""
    return f"unknown decision graph node: {node_id}"


def message_decision_graph_endpoint_unknown(node_id: str) -> str:
    """Return an unknown decision-graph edge endpoint message."""
    return f"unknown decision graph endpoint: {node_id}"


def message_unknown_agent_strategy(strategy_id: str) -> str:
    """Return an unknown agent strategy message."""
    return f"Unknown agent strategy: {strategy_id}"
