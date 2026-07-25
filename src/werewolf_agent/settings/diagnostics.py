"""Runtime diagnostics helpers."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from werewolf_agent.settings import APP_NAME, AppSettings, repository_root
from werewolf_agent.settings.constants import REDACTED


def build_entrypoint_diagnostics(
    *,
    settings: AppSettings,
    data_source: str,
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
        "data source": data_source,
        "data health": api_health,
        "supabase url": settings.supabase_url or "not configured",
        "supabase publishable key": (
            REDACTED if settings.supabase_publishable_key_value else "not configured"
        ),
        "supabase worker dsn": REDACTED if settings.supabase_db_dsn_value else "not configured",
        "provider": settings.llm_provider,
        "model": settings.model,
        "llm base url": settings.llm_base_url or "provider default",
        "llm api key": REDACTED if settings.configured_openai_api_key else "not configured",
        "prompt file": str(settings.llm_prompt_path or "packaged"),
        "player roster file": str(settings.llm_players_path or "packaged"),
        "fake responses file": str(settings.llm_fake_responses_path or "packaged"),
        "log level": settings.log_level,
        "log output": settings.log_output,
        "log dir": str(settings.log_directory_path),
        "log file": str(settings.log_file_path),
        "log retention days": str(settings.log_retention_days),
        "log third party level": settings.log_third_party_level,
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
        return ".env missing; packaged defaults are active"
    return ".env and .env.example missing"
