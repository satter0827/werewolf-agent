"""Observability startup helpers for application processes."""

from werewolf_agent.observability.logging import configure_observability
from werewolf_agent.settings import AppSettings, load_app_settings
from werewolf_agent.settings.defaults import DEFAULT_LOG_FILE_NAME


def configure_entrypoint_logging(
    settings: AppSettings | None = None,
    *,
    default_log_file_name: str | None = None,
    service_name: str | None = None,
) -> AppSettings:
    """Configure logging for an entry point process and return its settings."""
    loaded_settings = settings or load_app_settings()
    if default_log_file_name is not None and loaded_settings.log_file_name == DEFAULT_LOG_FILE_NAME:
        loaded_settings = loaded_settings.model_copy(
            update={"log_file_name": default_log_file_name}
        )
    configure_observability(loaded_settings, service_name=service_name)
    return loaded_settings
