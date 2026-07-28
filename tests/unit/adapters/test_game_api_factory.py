from datetime import UTC, datetime, timedelta

import pytest

from werewolf_agent.adapters import factory
from werewolf_agent.adapters.http import HttpGameClient
from werewolf_agent.adapters.supabase import SupabaseSession
from werewolf_agent.contracts import AppError
from werewolf_agent.settings import AppSettings


def test_build_game_client_requires_supabase_settings() -> None:
    with pytest.raises(AppError, match="WEREWOLF_SUPABASE_URL"):
        factory.build_game_client(AppSettings(_env_file=None))


def test_build_game_client_always_returns_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SupabaseSession(
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_id="user-1",
        email="",
        is_anonymous=True,
    )
    monkeypatch.setattr(factory, "ensure_session", lambda _settings: session)

    api = factory.build_game_client(
        AppSettings(
            _env_file=None,
            supabase_url="http://127.0.0.1:54321",
            supabase_publishable_key="anon-test",
        )
    )

    assert isinstance(api, HttpGameClient)
