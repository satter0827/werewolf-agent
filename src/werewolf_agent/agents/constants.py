"""agents constantsが所有する安定した値."""

from __future__ import annotations

from typing import Final

MIN_TIMEOUT_SECONDS_EXCLUSIVE: Final = 0

MIN_RETRY_COUNT: Final = 0

MIN_STEP_LIMIT: Final = 1

MIN_LLM_MAX_TOKENS: Final = 1

LLM_PROVIDER_LMSTUDIO: Final = "lmstudio"

LLM_PROVIDER_OPENAI: Final = "openai"

MIN_LLM_TEMPERATURE: Final = 0

MAX_LLM_TEMPERATURE: Final = 2

LLM_STRUCTURED_OUTPUT_MODE_AUTO: Final = "auto"

LLM_STRUCTURED_OUTPUT_MODE_DISABLED: Final = "disabled"

LLM_STRUCTURED_OUTPUT_MODE_REQUIRED: Final = "required"

LLM_STRUCTURED_OUTPUT_MODE_CHOICES: Final = (
    LLM_STRUCTURED_OUTPUT_MODE_AUTO,
    LLM_STRUCTURED_OUTPUT_MODE_DISABLED,
    LLM_STRUCTURED_OUTPUT_MODE_REQUIRED,
)

LLM_STRUCTURED_OUTPUT_MODE_CHOICE_SET: Final = frozenset(LLM_STRUCTURED_OUTPUT_MODE_CHOICES)

LLM_FALLBACK_POLICY_DETERMINISTIC_LEGAL_ACTION: Final = "deterministic_legal_action"

LLM_FALLBACK_POLICY_CHOICES: Final = (LLM_FALLBACK_POLICY_DETERMINISTIC_LEGAL_ACTION,)

LLM_FALLBACK_POLICY_CHOICE_SET: Final = frozenset(LLM_FALLBACK_POLICY_CHOICES)


MIN_VERSION: Final = 1

MIN_CHARACTER_AGE: Final = 18

MAX_CHARACTER_AGE: Final = 99

DECISION_GRAPH_START: Final = "START"

DECISION_GRAPH_END: Final = "END"

DECISION_GRAPH_NODE_IDS: Final = (
    "normalize_observation",
    "choose_required_action",
    "build_prompt_context",
    "role_hint",
    "rank_targets",
    "invoke_model",
    "validate_action",
    "repair_once",
    "deterministic_fallback",
)

DECISION_GRAPH_NODE_ID_SET: Final = frozenset(DECISION_GRAPH_NODE_IDS)
