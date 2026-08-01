"""OS credential-store backed Supabase session persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from platformdirs import user_config_path

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode

KEYRING_SERVICE_NAME: Final = "werewolf-agent"
LEGACY_SESSION_FILE_NAME: Final = "session.json"


@dataclass(frozen=True)
class SupabaseSession:
    """Provider-independent session value used by application adapters."""

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
    """Persist CLI sessions only in the operating-system credential store."""

    def __init__(
        self,
        supabase_url: str,
        *,
        backend: Any = keyring,
        legacy_path: Path | None = None,
    ) -> None:
        """Bind one normalized Supabase project to an OS credential account."""
        normalized_url = supabase_url.strip().rstrip("/").lower()
        self._account = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
        self._backend = backend
        self._legacy_path = legacy_path or (
            user_config_path("werewolf-agent", appauthor=False) / LEGACY_SESSION_FILE_NAME
        )

    def load(self) -> SupabaseSession | None:
        """Return the saved session after verifying keyring availability."""
        self._remove_legacy_session()
        value = self._read_password()
        if value is None:
            return None
        try:
            return _session_from_payload(json.loads(value))
        except (KeyError, TypeError, ValueError) as exc:
            raise _credential_error() from exc

    def save(self, session: SupabaseSession) -> None:
        """Save all session fields as one credential value."""
        self._remove_legacy_session()
        payload = asdict(session)
        payload["expires_at"] = session.expires_at.isoformat()
        try:
            self._backend.set_password(
                KEYRING_SERVICE_NAME,
                self._account,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
        except (KeyringError, RuntimeError) as exc:
            raise _credential_error() from exc

    def clear(self) -> None:
        """Remove the credential when present."""
        self._remove_legacy_session()
        try:
            self._backend.delete_password(KEYRING_SERVICE_NAME, self._account)
        except PasswordDeleteError:
            pass
        except (KeyringError, RuntimeError) as exc:
            raise _credential_error() from exc

    def _read_password(self) -> str | None:
        try:
            return cast(
                str | None,
                self._backend.get_password(KEYRING_SERVICE_NAME, self._account),
            )
        except (KeyringError, RuntimeError) as exc:
            raise _credential_error() from exc

    def _remove_legacy_session(self) -> None:
        try:
            self._legacy_path.unlink(missing_ok=True)
        except OSError as exc:
            raise _credential_error() from exc


def _session_from_payload(payload: Any) -> SupabaseSession:
    if not isinstance(payload, dict):
        raise ValueError("credential payload must be an object")
    access_token = _required_credential_text(payload, "access_token")
    refresh_token = _required_credential_text(payload, "refresh_token")
    user_id = _required_credential_text(payload, "user_id")
    expires_at = datetime.fromisoformat(str(payload["expires_at"]))
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("credential expiry must include a timezone")
    return SupabaseSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at.astimezone(UTC),
        user_id=user_id,
        email=str(payload.get("email") or ""),
        is_anonymous=bool(payload.get("is_anonymous", False)),
    )


def _required_credential_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload[key]).strip()
    if not value:
        raise ValueError(f"credential {key} must not be blank")
    return value


def _credential_error() -> AppError:
    return AppError(
        "OSのcredential storeを利用できません。",
        code=ErrorCode.API_UNAVAILABLE,
    )
