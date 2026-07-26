"""Stable protocol values for the LangChain adapter."""

from typing import Final

DETERMINISTIC_SELECTOR_BYTES: Final = 8
PROMPT_JSON_SEPARATORS: Final[tuple[str, str]] = (",", ":")
PROMPT_RECENT_SPEECH_LIMIT: Final = 3
PROMPT_RECENT_VOTE_ROUND_LIMIT: Final = 2
LLM_SPEECH_MESSAGE_MAX_CHARS: Final = 80
LLM_SPEECH_PROMPT_MAX_CHARS: Final = 60
SECONDS_TO_MILLISECONDS: Final = 1000
DECISION_GRAPH_REVISION: Final = "standard-v1"
DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION: Final = "normalize_observation"
DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION: Final = "choose_required_action"
DECISION_GRAPH_NODE_ROLE_HINT: Final = "role_hint"
DECISION_GRAPH_NODE_RANK_TARGETS: Final = "rank_targets"
DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT: Final = "build_prompt_context"
DECISION_GRAPH_NODE_INVOKE_MODEL: Final = "invoke_model"
DECISION_GRAPH_NODE_VALIDATE_ACTION: Final = "validate_action"
DECISION_GRAPH_NODE_REPAIR_ONCE: Final = "repair_once"
DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK: Final = "deterministic_fallback"
LLM_FALLBACK_POLICY_DETERMINISTIC_LEGAL_ACTION: Final = "deterministic_legal_action"
LLM_STRUCTURED_OUTPUT_MODE_DISABLED: Final = "disabled"
LLM_STRUCTURED_OUTPUT_MODE_REQUIRED: Final = "required"
VALIDATION_STATUS_VALID: Final = "valid"
VALIDATION_STATUS_INVALID: Final = "invalid"
VALIDATION_STATUS_FAILED: Final = "failed"
VALIDATION_STATUS_FALLBACK: Final = "fallback"
ROUTE_VALID: Final = "valid"
ROUTE_INVALID: Final = "invalid"
ROUTE_FAILED: Final = "failed"
ROUTE_FALLBACK: Final = "fallback"
ERROR_TYPE_GRAPH_INVOCATION: Final = "graph_invocation"
ERROR_TYPE_STRUCTURED_OUTPUT_UNSUPPORTED: Final = "structured_output_unsupported"
FALLBACK_REASON_MODEL_ERROR: Final = "model_error"
FALLBACK_REASON_REPAIR_FAILED: Final = "repair_failed"
DEFAULT_REPAIRED_SPEECH: Final = "I will watch the table and stay concise."
