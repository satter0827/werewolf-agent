"""Startup helpers for application interfaces."""

from __future__ import annotations

from pydantic import ValidationError

from werewolf_agent.configuration.messages import (
    MESSAGE_INVALID_APPLICATION_CONFIGURATION,
    MESSAGE_INVALID_VALUE,
    MESSAGE_SETTINGS,
    message_invalid_configuration_for,
)
from werewolf_agent.configuration.settings import AppSettings, get_settings


def load_app_settings() -> AppSettings:
    """Return validated application settings for entry points."""
    return get_settings()


def settings_error_detail(error: ValidationError) -> str:
    """Return a safe, user-facing description of a settings validation error."""
    issues = error.errors()
    if not issues:
        return MESSAGE_INVALID_APPLICATION_CONFIGURATION

    first_issue = issues[0]
    location = settings_error_location(first_issue.get("loc", ()))
    message = str(first_issue.get("msg", MESSAGE_INVALID_VALUE))
    return message_invalid_configuration_for(location, message)


def settings_error_location(location: object) -> str:
    """Return a dotted settings location from a Pydantic error location."""
    if isinstance(location, (tuple, list)):
        parts = [str(part) for part in location]
    elif location in (None, ""):
        parts = []
    else:
        parts = [str(location)]
    return ".".join(parts) if parts else MESSAGE_SETTINGS
