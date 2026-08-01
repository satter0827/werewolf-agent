from __future__ import annotations

import httpx
import pytest

from werewolf_agent.adapters.supabase.admin_session import SupabaseAdminSessionVerifier
from werewolf_agent.security.principal import AdminSessionUnavailable
from werewolf_agent.settings import AppSettings


def _active_session(_user_id: str, _session_id: str) -> bool:
    return True


def _verifier(
    handler: httpx.MockTransport,
    *,
    session_is_active=_active_session,
) -> SupabaseAdminSessionVerifier:
    return SupabaseAdminSessionVerifier(
        AppSettings(
            _env_file=None,
            supabase_url="https://project.supabase.co",
            supabase_publishable_key="publishable",
        ),
        session_is_active=session_is_active,
        transport=handler,
    )


def test_live_admin_session_requires_current_user_and_server_owned_role() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://project.supabase.co/auth/v1/user"
        assert request.headers["api" + "key"] == "publishable"
        assert request.headers["author" + "ization"] == "Bearer access-token"
        return httpx.Response(
            200,
            json={"id": "user-1", "app_metadata": {"role": "admin"}},
        )

    verifier = _verifier(httpx.MockTransport(handler))
    try:
        assert (
            verifier.verify(
                "access-token",
                expected_user_id="user-1",
                expected_session_id="session-1",
            )
            is True
        )
        assert (
            verifier.verify(
                "access-token",
                expected_user_id="other-user",
                expected_session_id="session-1",
            )
            is False
        )
    finally:
        verifier.close()


@pytest.mark.parametrize("status_code", [401, 403])
def test_revoked_or_rejected_session_is_not_admin(status_code: int) -> None:
    verifier = _verifier(httpx.MockTransport(lambda _request: httpx.Response(status_code)))
    try:
        assert (
            verifier.verify(
                "access-token",
                expected_user_id="user-1",
                expected_session_id="session-1",
            )
            is False
        )
    finally:
        verifier.close()


def test_auth_service_failure_is_distinct_from_rejected_session() -> None:
    verifier = _verifier(httpx.MockTransport(lambda _request: httpx.Response(503)))
    try:
        with pytest.raises(AdminSessionUnavailable):
            verifier.verify(
                "access-token",
                expected_user_id="user-1",
                expected_session_id="session-1",
            )
    finally:
        verifier.close()


def test_current_auth_metadata_can_remove_stale_token_admin_role() -> None:
    verifier = _verifier(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"id": "user-1", "app_metadata": {"role": "member"}},
            )
        )
    )
    try:
        assert (
            verifier.verify(
                "access-token",
                expected_user_id="user-1",
                expected_session_id="session-1",
            )
            is False
        )
    finally:
        verifier.close()


def test_revoked_exact_session_is_not_admin_even_with_valid_access_token() -> None:
    verifier = _verifier(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"id": "user-1", "app_metadata": {"role": "admin"}},
            )
        ),
        session_is_active=lambda _user_id, _session_id: False,
    )
    try:
        assert (
            verifier.verify(
                "access-token",
                expected_user_id="user-1",
                expected_session_id="revoked-session",
            )
            is False
        )
    finally:
        verifier.close()
