"""Shared startup helpers for user-facing interfaces."""

from __future__ import annotations

from pydantic import ValidationError

from werewolf_agent.commons.logging.config import (
    build_django_logging_config,
    configure_logging,
)
from werewolf_agent.configuration import AppSettings, get_settings


def load_app_settings() -> AppSettings:
    """Return validated application settings for interface entry points."""
    return get_settings()


def configure_interface_logging(settings: AppSettings | None = None) -> AppSettings:
    """Configure logging for an interface process and return the settings used."""
    loaded_settings = settings or load_app_settings()
    configure_logging(loaded_settings)
    return loaded_settings


def build_interface_django_logging_config(settings: AppSettings) -> dict[str, object]:
    """Return the Django LOGGING setting built from shared interface settings."""
    return build_django_logging_config(settings)


def settings_error_detail(error: ValidationError) -> str:
    """Return a safe, user-facing description of a settings validation error."""
    issues = error.errors()
    if not issues:
        return "Invalid application configuration."

    first_issue = issues[0]
    location = settings_error_location(first_issue.get("loc", ()))
    message = str(first_issue.get("msg", "Invalid value."))
    return f"Invalid configuration for {location}: {message}"


def settings_error_location(location: object) -> str:
    """Return a dotted settings location from a Pydantic error location."""
    if isinstance(location, (tuple, list)):
        parts = [str(part) for part in location]
    elif location in (None, ""):
        parts = []
    else:
        parts = [str(location)]
    return ".".join(parts) if parts else "settings"
