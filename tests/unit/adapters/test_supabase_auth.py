from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from keyring.errors import NoKeyringError

from werewolf_agent.adapters import auth
from werewolf_agent.adapters.supabase import auth_client, session_store
from werewolf_agent.adapters.supabase.auth_client import MfaEnrollment, MfaFactor
from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.contracts import AppError
from werewolf_agent.settings import AppSettings


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


def test_totp_verification_replaces_aal1_session(monkeypatch) -> None:
    member = _session(access_token="aal1")
    elevated = _session(access_token="aal2")
    store = _Store(member)
    fake_client = _AuthClient(elevated)
    fake_client.factors = (MfaFactor(id="factor-1", friendly_name="phone"),)
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    factors = auth.list_totp_factors(_settings(), store=store)
    session = auth.verify_totp(
        _settings(),
        factors[0].id,
        "123456",
        store=store,
    )

    assert session == elevated
    assert store.session == elevated
    assert fake_client.totp_verification == (member, "factor-1", "123456")


def test_invalid_totp_code_is_rejected_before_provider_call(monkeypatch) -> None:
    fake_client = _AuthClient(_session(access_token="aal2"))
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    with pytest.raises(AppError, match="6桁"):
        auth.verify_totp(
            _settings(),
            "factor-1",
            "12345x",
            store=_Store(_session(access_token="aal1")),
        )

    assert fake_client.totp_verification is None


def test_totp_enrollment_returns_only_current_setup_material(monkeypatch) -> None:
    fake_client = _AuthClient(_session())
    monkeypatch.setattr(auth, "_auth_client", lambda _settings: fake_client)

    enrollment = auth.enroll_totp(
        _settings(),
        friendly_name=" operator phone ",
        store=_Store(_session()),
    )

    assert enrollment.factor_id == "factor-new"
    assert fake_client.enrollment_name == "operator phone"


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


def test_session_store_uses_project_scoped_os_credential(tmp_path) -> None:
    path = tmp_path / "auth" / "session.json"
    path.parent.mkdir()
    path.write_text("legacy-token", encoding="utf-8")
    backend = _Keyring()
    store = session_store.SupabaseSessionStore(
        "HTTPS://PROJECT.SUPABASE.CO/",
        backend=backend,
        legacy_path=path,
    )
    expected = _session()

    store.save(expected)

    assert store.load() == expected
    assert not path.exists()
    assert backend.service == "werewolf-agent"
    assert len(backend.account) == 64
    assert "refresh" in backend.value


def test_session_store_does_not_fallback_when_keyring_is_unavailable(tmp_path) -> None:
    class UnavailableKeyring(_Keyring):
        def get_password(self, service: str, account: str) -> str | None:
            del service, account
            raise NoKeyringError("private backend detail")

    legacy = tmp_path / "session.json"
    legacy.write_text("legacy-token", encoding="utf-8")
    store = session_store.SupabaseSessionStore(
        "https://project.supabase.co",
        backend=UnavailableKeyring(),
        legacy_path=legacy,
    )

    with pytest.raises(AppError) as exc_info:
        store.load()

    assert "private backend detail" not in str(exc_info.value)
    assert not legacy.exists()


@pytest.mark.parametrize(
    "credential",
    [
        "{}",
        '{"access_token":"","refresh_token":"refresh","expires_at":"2026-01-01T00:00:00+00:00","user_id":"user-1"}',
        '{"access_token":"access","refresh_token":"refresh","expires_at":"2026-01-01T00:00:00","user_id":"user-1"}',
    ],
)
def test_session_store_maps_invalid_credentials_to_safe_error(credential: str) -> None:
    backend = _Keyring()
    backend.value = credential
    store = session_store.SupabaseSessionStore(
        "https://project.supabase.co",
        backend=backend,
    )

    with pytest.raises(AppError) as exc_info:
        store.load()

    assert "access_token" not in str(exc_info.value)
    assert "expires_at" not in str(exc_info.value)


def test_auth_sdk_session_uses_an_expiry_safety_margin() -> None:
    provider_expiry = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    response = SimpleNamespace(
        session=SimpleNamespace(
            access_token="access",
            refresh_token="refresh",
            expires_at=provider_expiry,
            expires_in=3600,
            user=SimpleNamespace(
                id="user-1",
                email="player@example.test",
                is_anonymous=False,
            ),
        )
    )

    session = auth_client._session_from_response(response)  # type: ignore[arg-type]

    assert session.expires_at == datetime.fromtimestamp(provider_expiry - 30, UTC)


def test_auth_sdk_session_rejects_blank_credentials() -> None:
    response = SimpleNamespace(
        session=SimpleNamespace(
            access_token="",
            refresh_token="refresh",
            expires_at=None,
            expires_in=3600,
            user=SimpleNamespace(id="user-1", email=None, is_anonymous=True),
        )
    )

    with pytest.raises(AppError):
        auth_client._session_from_response(response)  # type: ignore[arg-type]


def test_auth_sdk_uses_explicit_session_for_totp_flow() -> None:
    sdk = _SdkClient()
    client = auth_client.SupabaseAuthClient(
        "https://project.supabase.co",
        "publishable",
        timeout=1,
        client=sdk,
    )
    member = _session(access_token="aal1")

    factors = client.list_totp_factors(member)
    enrollment = client.enroll_totp(member, friendly_name="operator phone")
    elevated = client.verify_totp(
        member,
        factor_id="factor-1",
        code="123456",
    )

    assert factors == (MfaFactor(id="factor-1", friendly_name="phone"),)
    assert enrollment.factor_id == "factor-new"
    assert elevated.access_token == "aal2"
    assert sdk.sessions == [("aal1", "refresh")] * 3
    assert sdk.mfa.verification == {"factor_id": "factor-1", "code": "123456"}


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


class _Keyring:
    def __init__(self) -> None:
        self.service = ""
        self.account = ""
        self.value: str | None = None

    def get_password(self, service: str, account: str) -> str | None:
        self.service = service
        self.account = account
        return self.value

    def set_password(self, service: str, account: str, value: str) -> None:
        self.service = service
        self.account = account
        self.value = value

    def delete_password(self, service: str, account: str) -> None:
        self.service = service
        self.account = account
        self.value = None


class _AuthClient:
    def __init__(self, session: SupabaseSession) -> None:
        self.session = session
        self.refreshed: SupabaseSession | None = None
        self.anonymous_created = False
        self.password_credentials: tuple[str, str] | None = None
        self.signed_out: SupabaseSession | None = None
        self.factors: tuple[MfaFactor, ...] = ()
        self.totp_verification: tuple[SupabaseSession, str, str] | None = None
        self.enrollment_name: str | None = None

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

    def list_totp_factors(self, session: SupabaseSession) -> tuple[MfaFactor, ...]:
        del session
        return self.factors

    def enroll_totp(
        self,
        session: SupabaseSession,
        *,
        friendly_name: str,
    ) -> MfaEnrollment:
        del session
        self.enrollment_name = friendly_name
        return MfaEnrollment(
            factor_id="factor-new",
            uri="otpauth://example",
        )

    def verify_totp(
        self,
        session: SupabaseSession,
        *,
        factor_id: str,
        code: str,
    ) -> SupabaseSession:
        self.totp_verification = (session, factor_id, code)
        return self.session


class _SdkMfa:
    def __init__(self) -> None:
        self.verification: dict[str, str] | None = None

    def list_factors(self) -> SimpleNamespace:
        return SimpleNamespace(totp=[SimpleNamespace(id="factor-1", friendly_name="phone")])

    def enroll(self, params: dict[str, str]) -> SimpleNamespace:
        assert params == {"factor_type": "totp", "friendly_name": "operator phone"}
        return SimpleNamespace(
            id="factor-new",
            totp=SimpleNamespace(
                qr_code="qr",
                uri="otpauth://example",
            ),
        )

    def challenge_and_verify(self, params: dict[str, str]) -> SimpleNamespace:
        self.verification = params
        return SimpleNamespace(
            access_token="aal2",
            refresh_token="refresh-2",
            expires_in=3600,
            user=SimpleNamespace(
                id="user-1",
                email="player@example.test",
                is_anonymous=False,
            ),
        )


class _SdkClient:
    def __init__(self) -> None:
        self.mfa = _SdkMfa()
        self.sessions: list[tuple[str, str]] = []

    def set_session(self, access_token: str, refresh_token: str) -> None:
        self.sessions.append((access_token, refresh_token))


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
