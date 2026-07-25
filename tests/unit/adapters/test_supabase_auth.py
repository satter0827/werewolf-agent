from datetime import UTC, datetime, timedelta

import pytest

from werewolf_agent.adapters import auth
from werewolf_agent.adapters.supabase import SupabaseSession, session_store
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


def test_password_sign_in_replaces_interface_session(monkeypatch) -> None:
    member = _session(access_token="member")
    store = _Store(_session(access_token="guest", is_anonymous=True))
    fake_client = _AuthClient(member)
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    session = auth.sign_in_with_password(
        _settings(),
        " player@example.test ",
        "password",
        store=store,
    )

    assert session == member
    assert store.session == member
    assert fake_client.password_credentials == ("player@example.test", "password")


def test_sign_out_replaces_member_session_with_guest(monkeypatch) -> None:
    member = _session(access_token="member")
    guest = _session(access_token="guest", is_anonymous=True)
    store = _Store(member)
    fake_client = _AuthClient(guest)
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    session = auth.sign_out(_settings(), store=store)

    assert session == guest
    assert fake_client.signed_out == member
    assert store.cleared is True
    assert store.session == guest


def test_session_store_writes_atomically_with_owner_only_permissions(
    tmp_path,
    monkeypatch,
) -> None:
    protected: list[tuple[object, int]] = []
    monkeypatch.setattr(
        session_store,
        "_restrict_to_owner",
        lambda path, mode: protected.append((path, mode)),
    )
    path = tmp_path / "auth" / "session.json"
    store = session_store.SupabaseSessionStore(path)
    expected = _session()

    store.save(expected)

    assert store.load() == expected
    assert not path.with_suffix(".json.tmp").exists()
    assert [mode for _, mode in protected] == [0o700, 0o600, 0o600]


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
        self.password_credentials: tuple[str, str] | None = None
        self.signed_out: SupabaseSession | None = None

    def refresh(self, session: SupabaseSession) -> SupabaseSession:
        self.refreshed = session
        return self.session

    def sign_in_anonymously(self) -> SupabaseSession:
        self.anonymous_created = True
        return self.session

    def sign_in_with_password(self, email: str, password: str) -> SupabaseSession:
        self.password_credentials = (email, password)
        return self.session

    def sign_out(self, session: SupabaseSession) -> None:
        self.signed_out = session


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        supabase_url="http://127.0.0.1:54321",
        supabase_publishable_key="anon-test",
    )


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
