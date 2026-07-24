from datetime import UTC, datetime, timedelta

import pytest

from werewolf_agent.adapters import auth
from werewolf_agent.adapters.supabase import SupabaseSession
from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts import AppError


def test_ensure_session_requires_supabase_client_settings() -> None:
    with pytest.raises(AppError, match="WEREWOLF_SUPABASE_URL"):
        auth.ensure_session(
            AppSettings(_env_file=None),
            store=_Store(None),
        )


def test_ensure_session_refreshes_expired_session(monkeypatch) -> None:
    expired = _session(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    refreshed = _session(access_token="fresh")
    store = _Store(expired)
    fake_client = _AuthClient(refreshed)
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    session = auth.ensure_session(
        AppSettings(
            _env_file=None,
            supabase_url="http://127.0.0.1:54321",
            supabase_publishable_key="anon-test",
        ),
        store=store,
    )

    assert session == refreshed
    assert store.saved == refreshed
    assert fake_client.refreshed == expired


def test_ensure_session_creates_anonymous_session_when_missing(monkeypatch) -> None:
    created = _session(access_token="anonymous", is_anonymous=True)
    store = _Store(None)
    fake_client = _AuthClient(created)
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    session = auth.ensure_session(
        AppSettings(
            _env_file=None,
            supabase_url="http://127.0.0.1:54321",
            supabase_publishable_key="anon-test",
        ),
        store=store,
    )

    assert session == created
    assert store.saved == created
    assert fake_client.anonymous_created is True


class _Store:
    def __init__(self, session: SupabaseSession | None) -> None:
        self.session = session
        self.saved: SupabaseSession | None = None
        self.cleared = False

    def load(self) -> SupabaseSession | None:
        return self.session

    def save(self, session: SupabaseSession) -> None:
        self.saved = session
        self.session = session

    def clear(self) -> None:
        self.cleared = True
        self.session = None


class _AuthClient:
    def __init__(self, session: SupabaseSession) -> None:
        self.session = session
        self.refreshed: SupabaseSession | None = None
        self.anonymous_created = False

    def refresh(self, session: SupabaseSession) -> SupabaseSession:
        self.refreshed = session
        return self.session

    def sign_in_anonymously(self) -> SupabaseSession:
        self.anonymous_created = True
        return self.session


def _session(
    *,
    access_token: str = "access",
    expires_at: datetime | None = None,
    is_anonymous: bool = False,
) -> SupabaseSession:
    return SupabaseSession(
        access_token=access_token,
        refresh_token="refresh",
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
        user_id="user-1",
        email="player@example.test",
        is_anonymous=is_anonymous,
    )
