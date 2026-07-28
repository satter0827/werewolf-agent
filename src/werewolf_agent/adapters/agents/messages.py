"""adapters agents messagesが所有する文言."""

from __future__ import annotations

MESSAGE_MISSING_SPEECH_MESSAGE = "missing speech message"

MESSAGE_MISSING_VOTE_TARGET = "missing vote target"

MESSAGE_MISSING_ATTACK_TARGET = "missing attack target"

MESSAGE_MISSING_INSPECT_TARGET = "missing inspect target"

MESSAGE_MISSING_GUARD_TARGET = "missing guard target"


def message_unsupported_llm_provider(provider: str) -> str:
    """Return an unsupported LLM provider configuration message."""
    return f"Unsupported LLM provider: {provider}."


def message_langchain_openai_required(*, lmstudio_provider: str, openai_provider: str) -> str:
    """Return a LangChain provider dependency message."""
    return (
        f"langchain-openai is required for {lmstudio_provider} and {openai_provider} LLM providers"
    )
