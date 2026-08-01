"""Mapping from runtime settings to application context."""

from __future__ import annotations

from dataclasses import replace

from werewolf_agent.adapters.constants import (
    LLM_PROVIDER_LMSTUDIO,
    LLM_STUDIO_API_KEY_PLACEHOLDER,
)
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.messages import (
    message_definition_settings_invalid,
)
from werewolf_agent.adapters.resources import (
    LlmDefinitions,
    load_llm_definitions,
    load_setup_template_catalog,
)
from werewolf_agent.application.models import GameApplicationConfig
from werewolf_agent.application.setup_catalog import SetupTemplateCatalog
from werewolf_agent.settings import AppSettings, get_settings


def build_game_application_config(settings: AppSettings | None = None) -> GameApplicationConfig:
    """Return application configuration from runtime settings.

    Args:
        settings: Optional preloaded application settings. When omitted, settings are loaded from
            the default runtime sources.

    Returns:
        Application configuration without entry point-only settings.

    """
    app_settings = settings or get_settings()
    return GameApplicationConfig(
        min_players=app_settings.game_min_players,
        max_players=app_settings.game_max_players,
        game_list_default_limit=app_settings.api_game_list_default_limit,
        game_list_max_limit=app_settings.api_game_list_max_limit,
        timeline_default_limit=app_settings.api_timeline_default_limit,
        timeline_max_limit=app_settings.api_timeline_max_limit,
        setup_revision_default_limit=app_settings.api_setup_revision_default_limit,
        setup_revision_max_limit=app_settings.api_setup_revision_max_limit,
        setup_list_default_limit=app_settings.api_setup_list_default_limit,
        setup_list_max_limit=app_settings.api_setup_list_max_limit,
        setup_max_saved_setups=app_settings.game_setup_max_saved_setups,
        setup_max_revisions=app_settings.game_setup_max_revisions,
    )


def build_llm_provider_config(settings: AppSettings | None = None) -> LlmProviderConfig:
    """Return LLM provider configuration from application settings.

    Args:
        settings: Optional preloaded application settings. When omitted, settings are loaded from
            the default runtime sources.

    Returns:
        LLM provider configuration for automated players.

    """
    app_settings = settings or get_settings()
    api_key = app_settings.configured_openai_api_key
    if app_settings.llm_provider == LLM_PROVIDER_LMSTUDIO and not api_key:
        api_key = LLM_STUDIO_API_KEY_PLACEHOLDER
    return LlmProviderConfig(
        provider=app_settings.llm_provider,
        model=app_settings.model,
        base_url=app_settings.llm_base_url,
        api_key=api_key,
        timeout_seconds=app_settings.llm_timeout_seconds,
        max_retries=app_settings.llm_max_retries,
        max_tokens=app_settings.llm_max_tokens,
        temperature=app_settings.llm_temperature,
        model_catalog_max_bytes=app_settings.llm_model_catalog_max_bytes,
    )


def build_worker_llm_provider_config(
    llm_mode: str,
    settings: AppSettings | None = None,
) -> LlmProviderConfig:
    """Return a worker-only provider config for an immutable game LLM mode."""
    app_settings = settings or get_settings()
    base = build_llm_provider_config(app_settings)
    if llm_mode == "fake":
        return replace(
            base,
            provider="fake",
            model="fake-list-chat-model",
            base_url="",
            api_key="",
        )
    if llm_mode == "paid":
        return replace(
            base,
            provider=app_settings.worker_paid_llm_provider,
            model=app_settings.worker_paid_llm_model,
            base_url=app_settings.worker_paid_llm_base_url,
            api_key=app_settings.configured_openai_api_key,
        )
    raise ValueError("llm_mode must be fake or paid.")


def build_setup_catalog(settings: AppSettings | None = None) -> SetupTemplateCatalog:
    """Return validated complete setup templates."""
    _ = settings
    try:
        return load_setup_template_catalog()
    except Exception as exc:
        raise ValueError(message_definition_settings_invalid(exc)) from exc


def build_llm_definitions(settings: AppSettings | None = None) -> LlmDefinitions:
    """Return loaded LLM definitions from application settings."""
    app_settings = settings or get_settings()
    try:
        definitions = load_llm_definitions(
            prompt_path=app_settings.llm_prompt_path,
            fake_responses_path=app_settings.llm_fake_responses_path,
        )
    except Exception as exc:
        raise ValueError(message_definition_settings_invalid(exc)) from exc
    return definitions
