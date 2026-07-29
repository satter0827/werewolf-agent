"""公開application facadeの例外契約。"""

from __future__ import annotations

from typing import Any, NoReturn, cast

import pytest

from werewolf_agent import application
from werewolf_agent.application import handlers
from werewolf_agent.application.errors import GameNotFoundError


class _Repository:
    """例外境界だけを検証する空repository。"""


class _AllowPolicy:
    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        del game_id, user_id

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        del game_id, player_id, user_id


class _DenyPolicy(_AllowPolicy):
    def require_game_access(self, game_id: str, *, user_id: str) -> NoReturn:
        del game_id, user_id
        raise PermissionError("internal authorization failure")


def _config() -> application.GameApplicationConfig:
    return application.GameApplicationConfig(
        min_players=4,
        max_players=16,
        game_list_default_limit=20,
        game_list_max_limit=100,
        timeline_default_limit=50,
        timeline_max_limit=200,
    )


def _games(*, policy: object | None = None) -> application.GameApplication:
    context = application.ApplicationContext(
        repository=cast(application.GameRepository, _Repository()),
        config=_config(),
    )
    return application.GameApplication(
        context,
        access_policy=cast(application.AccessPolicy | None, policy),
    )


def test_public_facade_converts_authorization_failures_to_app_error() -> None:
    """内部policyの認可拒否を安定した公開codeへ変換する。"""
    games = _games(policy=_DenyPolicy())

    with pytest.raises(application.AppError) as captured:
        games.get("game-id", application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.AUTHORIZATION_FAILED


def test_public_facade_converts_missing_games_to_resource_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handlerの内部不存在例外を公開resource例外へ変換する。"""

    def missing(*_args: object, **_kwargs: object) -> NoReturn:
        raise GameNotFoundError("private repository detail")

    monkeypatch.setattr(handlers, "get_game", missing)
    games = _games(policy=_AllowPolicy())

    with pytest.raises(application.ResourceNotFoundError) as captured:
        games.get("game-id", application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.RESOURCE_NOT_FOUND
    assert "private repository detail" not in str(captured.value)


def test_public_facade_reports_missing_capabilities_as_config_errors() -> None:
    """任意portの構成不足をRuntimeErrorとして漏らさない。"""
    games = _games(policy=_AllowPolicy())

    with pytest.raises(application.ConfigError):
        games.operation("operation-id", application.Actor("user-id"))
    with pytest.raises(application.ConfigError):
        games.verify_replay("game-id", application.Actor("admin-id", is_admin=True))
    setups = application.SetupApplication(
        cast(Any, object()),
        _config(),
    )
    with pytest.raises(application.ConfigError):
        setups.list_setups(application.Actor("user-id"))


def test_public_facade_preserves_game_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """予定されたゲーム操作違反を公開GameErrorのまま返す。"""

    def invalid(*_args: object, **_kwargs: object) -> NoReturn:
        raise application.GameError("操作できません。")

    monkeypatch.setattr(handlers, "advance_game", invalid)
    games = _games(policy=_AllowPolicy())

    with pytest.raises(application.GameError):
        games.advance("game-id", application.Actor("user-id"), 1)


def test_public_facade_rejects_non_admin_with_authorization_code() -> None:
    """管理者操作の拒否をPermissionErrorとして漏らさない。"""
    games = _games(policy=_AllowPolicy())

    with pytest.raises(application.AppError) as captured:
        games.reveal("game-id", application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.AUTHORIZATION_FAILED
