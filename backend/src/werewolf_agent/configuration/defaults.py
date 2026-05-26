"""Default values for process-level configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Final

APP_NAME: Final = "werewolf-agent"
API_SERVICE_NAME: Final = "werewolf-agent-api"

DEFAULT_LLM_PROVIDER: Final = "dummy"
DEFAULT_LLM_MODEL: Final = "dummy-local"

DEFAULT_LOG_LEVEL: Final = "INFO"
DEFAULT_LOG_FORMAT: Final = "json"
DEFAULT_LOG_OUTPUT: Final = "stderr"

DEFAULT_GENERATED_DIR: Final = Path(".werewolf-agent")
DEFAULT_DJANGO_SQLITE_PATH: Final = DEFAULT_GENERATED_DIR / "db" / "db.sqlite3"
DEFAULT_DJANGO_STATIC_ROOT: Final = DEFAULT_GENERATED_DIR / "staticfiles"
DEFAULT_DJANGO_SECRET_KEY: Final = "django-insecure-local-dev-only"
MIN_DJANGO_SECRET_KEY_LENGTH: Final = 50

DEFAULT_GAME_MIN_PLAYERS: Final = 5
DEFAULT_GAME_MAX_PLAYERS: Final = 8
DEFAULT_GAME_DEFAULT_PLAYER_COUNT: Final = 6
DEFAULT_GAME_SUPPORTED_AGENT_TYPE: Final = "dummy"
DEFAULT_GAME_SUPPORTED_AGENT_NAME: Final = "Dummy Agent"
DEFAULT_GAME_DEFAULT_RULESET_ID: Final = "default"
DEFAULT_GAME_DEFAULT_RULESET_NAME: Final = "MVP Default"
DEFAULT_GAME_DEFAULT_RULESET_DESCRIPTION: Final = "5〜8人向けの最小同期 API ルールセットです。"
