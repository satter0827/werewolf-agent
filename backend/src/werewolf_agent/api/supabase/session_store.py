"""OS user scoped Supabase session persistence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from werewolf_agent.commons.shared.constants import JSON_ENCODING

SESSION_FILE_NAME: Final = "session.json"
APP_DIR_NAME: Final = "werewolf-agent"


@dataclass(frozen=True)
class SupabaseSession:
    """Authenticated Supabase session safe to keep in the OS user profile."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    user_id: str
    email: str
    is_anonymous: bool = False

    @property
    def is_expired(self) -> bool:
        """Return whether the access token should be refreshed."""
        return datetime.now(UTC) >= self.expires_at


class SupabaseSessionStore:
    """Persist CLI sessions outside the repository."""

    def __init__(self, path: Path | None = None) -> None:
        """Create a store at an explicit or OS default path."""
        self.path = path or default_session_path()

    def load(self) -> SupabaseSession | None:
        """Return the saved session, or `None` when absent/invalid."""
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding=JSON_ENCODING))
        except (OSError, ValueError):
            return None
        return _session_from_payload(payload)

    def save(self, session: SupabaseSession) -> None:
        """Save a session in the OS user profile."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_at": session.expires_at.isoformat(),
            "user_id": session.user_id,
            "email": session.email,
            "is_anonymous": session.is_anonymous,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding=JSON_ENCODING,
        )

    def clear(self) -> None:
        """Remove a saved session if it exists."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            return


def default_session_path() -> Path:
    """Return the OS-native session file path."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME / SESSION_FILE_NAME
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / APP_DIR_NAME / SESSION_FILE_NAME
    return Path.home() / ".config" / APP_DIR_NAME / SESSION_FILE_NAME


def _session_from_payload(payload: Any) -> SupabaseSession | None:
    if not isinstance(payload, dict):
        return None
    try:
        return SupabaseSession(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            expires_at=datetime.fromisoformat(str(payload["expires_at"])),
            user_id=str(payload["user_id"]),
            email=str(payload.get("email") or ""),
            is_anonymous=bool(payload.get("is_anonymous", False)),
        )
    except (KeyError, ValueError, TypeError):
        return None
