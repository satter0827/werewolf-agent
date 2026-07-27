"""Stable protocol values for the LangChain adapter."""

from typing import Final

DETERMINISTIC_SELECTOR_BYTES: Final = 8
LLM_SPEECH_MESSAGE_MAX_CHARS: Final = 80
SECONDS_TO_MILLISECONDS: Final = 1000
VALIDATION_STATUS_VALID: Final = "valid"
VALIDATION_STATUS_FALLBACK: Final = "fallback"
DEFAULT_FALLBACK_SPEECH: Final = "I will watch the table and stay concise."
