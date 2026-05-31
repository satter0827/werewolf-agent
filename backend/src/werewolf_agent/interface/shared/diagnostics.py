"""Shared interface diagnostics helpers."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from werewolf_agent.commons.shared.constants import REDACTED
from werewolf_agent.interface.runtime import APP_NAME, AppSettings, repository_root


def build_interface_diagnostics(
    *,
    settings: AppSettings,
    api_url: str,
    api_health: str,
) -> dict[str, str]:
    """Build user-facing diagnostics shared by CLI and Streamlit."""
    root = repository_root()
    return {
        "package": f"{APP_NAME} {package_version()}",
        "python": sys.version.split()[0],
        "python executable": sys.executable,
        "platform": platform.platform(),
        "repository": str(root),
        "env file": env_file_status(root),
        "api url": api_url,
        "api health": api_health,
        "provider": settings.llm_provider,
        "model": settings.model,
        "prompt file": str(settings.llm_prompt_path or "packaged"),
        "player roster file": str(settings.llm_players_path or "packaged"),
        "fake responses file": str(settings.llm_fake_responses_path or "packaged"),
        "log level": settings.log_level,
        "log output": settings.log_output,
        "log dir": str(settings.log_directory_path),
        "log file": str(settings.log_file_path),
        "log retention days": str(settings.log_retention_days),
        "log third party level": settings.log_third_party_level,
        "database": redacted_database_url(settings.sqlalchemy_database_url),
    }


def package_version() -> str:
    """Return the installed package version or editable marker."""
    try:
        return version(APP_NAME)
    except PackageNotFoundError:
        return "editable"


def env_file_status(root: Path) -> str:
    """Return a short .env status line."""
    env_path = root / ".env"
    example_path = root / ".env.example"

    if env_path.exists():
        return ".env found"
    if example_path.exists():
        return ".env missing; copy .env.example when enabling real providers"
    return ".env and .env.example missing"


def redacted_database_url(value: str) -> str:
    """Return a database URL safe for diagnostics output."""
    parsed = urlsplit(value)
    if parsed.password is None:
        return value

    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"

    user = parsed.username or ""
    credentials = f"{user}:{REDACTED}" if user else REDACTED
    return urlunsplit(
        (parsed.scheme, f"{credentials}@{host}", parsed.path, parsed.query, parsed.fragment)
    )
