from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from werewolf_agent.security.principal import (
    AdminSessionUnavailable,
    SupabaseJwtAuthenticator,
)
from werewolf_agent.settings import AppSettings


class _Verifier:
    def __init__(self, *, result: bool = True, unavailable: bool = False) -> None:
        self.result = result
        self.unavailable = unavailable
        self.calls: list[tuple[str, str]] = []

    def verify(self, token: str, *, expected_user_id: str) -> bool:
        self.calls.append((token, expected_user_id))
        if self.unavailable:
            raise AdminSessionUnavailable
        return self.result


def _authenticate(
    monkeypatch: pytest.MonkeyPatch,
    claims: dict[str, Any],
    *,
    verifier: _Verifier | None = None,
    now: float = 10_000,
):
    jwt_module = SimpleNamespace(
        PyJWKClient=lambda *_args, **_kwargs: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key="public-key")
        ),
        decode=lambda *_args, **_kwargs: claims,
    )
    monkeypatch.setitem(sys.modules, "jwt", jwt_module)
    authenticator = SupabaseJwtAuthenticator(
        AppSettings(
            _env_file=None,
            supabase_url="https://project.supabase.co",
            supabase_publishable_key="publishable",
            api_admin_max_token_age_seconds=3600,
        ),
        admin_session_verifier=verifier,
        clock=lambda: now,
    )
    return authenticator.authenticate("access-token")


def _claims(**overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "sub": "user-1",
        "iat": 9_500,
        "app_metadata": {"role": "admin"},
        "role": "authenticated",
        "aal": "aal2",
        "session_id": "session-1",
        "is_anonymous": False,
    }
    claims.update(overrides)
    return claims


def test_admin_requires_live_matching_auth_session(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = _Verifier()

    principal = _authenticate(monkeypatch, _claims(), verifier=verifier)

    assert principal.is_admin is True
    assert verifier.calls == [("access-token", "user-1")]


def test_admin_token_is_accepted_at_configured_age_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _Verifier()

    principal = _authenticate(monkeypatch, _claims(iat=6_400), verifier=verifier)

    assert principal.is_admin is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_metadata": {}},
        {"role": "service_role", "app_metadata": {}},
        {"aal": "aal1"},
        {"session_id": ""},
        {"is_anonymous": True},
        {"iat": 6_399},
    ],
)
def test_untrusted_or_weak_claims_never_enter_admin_verification(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any],
) -> None:
    verifier = _Verifier()

    principal = _authenticate(monkeypatch, _claims(**overrides), verifier=verifier)

    assert principal.is_admin is False
    assert verifier.calls == []


@pytest.mark.parametrize(
    "verifier",
    [_Verifier(result=False), _Verifier(unavailable=True)],
)
def test_revoked_or_unverifiable_admin_session_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    verifier: _Verifier,
) -> None:
    principal = _authenticate(monkeypatch, _claims(), verifier=verifier)

    assert principal.is_admin is False


def test_normal_user_does_not_depend_on_live_auth_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _Verifier(unavailable=True)

    principal = _authenticate(
        monkeypatch,
        _claims(app_metadata={"role": "member"}),
        verifier=verifier,
    )

    assert principal.user_id == "user-1"
    assert principal.is_admin is False
    assert verifier.calls == []
