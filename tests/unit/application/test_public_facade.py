"""公開application facadeの例外契約。"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any, NoReturn, cast

import pytest

from werewolf_agent import application
from werewolf_agent.application import handlers
from werewolf_agent.application.errors import GameNotFoundError, InvalidGameIdError
from werewolf_agent.domain import CoreRulePack, RulePolicyRegistry


class _Repository:
    """例外境界だけを検証する空repository。"""

    def transaction(self) -> AbstractContextManager[None]:
        return nullcontext()


class _ReplayRepository(_Repository):
    def replay_records(self, game_id: str) -> dict[str, list[object]]:
        del game_id
        return {"commands": [], "events": [], "states": []}


class _FailingQueue:
    def get(self, operation_id: str, *, owner_user_id: str) -> NoReturn:
        del operation_id, owner_user_id
        raise PermissionError("private queue detail")


class _MissingQueue:
    def get(self, operation_id: str, *, owner_user_id: str) -> None:
        del operation_id, owner_user_id


class _FailingSetupRepository:
    def list_setups(self, *, owner_user_id: str) -> NoReturn:
        del owner_user_id
        raise RuntimeError("postgresql://private-host/database")


class _InvalidSetupRepository:
    def list_setups(self, *, owner_user_id: str) -> NoReturn:
        del owner_user_id
        raise ValueError("persisted setup row is invalid")


class _AllowPolicy:
    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        del game_id, user_id

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        del game_id, player_id, user_id


class _DenyPolicy(_AllowPolicy):
    def require_game_access(self, game_id: str, *, user_id: str) -> NoReturn:
        del game_id, user_id
        raise PermissionError("internal authorization failure")


class _FailingPolicy(_AllowPolicy):
    def require_game_access(self, game_id: str, *, user_id: str) -> NoReturn:
        del game_id, user_id
        raise RuntimeError("policy_backend=private")


def _config() -> application.GameApplicationConfig:
    return application.GameApplicationConfig(
        min_players=4,
        max_players=16,
        game_list_default_limit=20,
        game_list_max_limit=100,
        timeline_default_limit=50,
        timeline_max_limit=200,
    )


def _games(
    *,
    policy: object | None = None,
    repository: object | None = None,
    queue: object | None = None,
) -> application.GameApplication:
    context = application.ApplicationContext(
        repository=cast(application.GameRepository, repository or _Repository()),
        config=_config(),
        rule_packs=RulePolicyRegistry((CoreRulePack(),)),
    )
    return application.GameApplication(
        context,
        access_policy=cast(application.AccessPolicy | None, policy),
        operation_queue=cast(application.OperationQueue | None, queue),
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


def test_public_facade_hides_unexpected_runtime_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """内部RuntimeErrorを安全な公開失敗へ変換する。"""

    def failed(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("postgresql://private-host/database")

    monkeypatch.setattr(handlers, "list_games", failed)

    with pytest.raises(application.InternalError) as captured:
        _games().list(application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.INTERNAL_UNEXPECTED
    assert "private-host" not in str(captured.value)
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_public_facade_hides_access_policy_runtime_details() -> None:
    """Access policyの内部失敗を安全な公開失敗へ変換する。"""
    games = _games(policy=_FailingPolicy())

    with pytest.raises(application.InternalError) as captured:
        games.get("game-id", application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.INTERNAL_UNEXPECTED
    assert "policy_backend" not in str(captured.value)


@pytest.mark.parametrize("failure", [KeyError("private-key"), OSError("private-path")])
def test_public_facade_hides_all_unexpected_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    """例外型の列挙へ依存せず、予期しない内部障害を安全化する。"""

    def failed(*_args: object, **_kwargs: object) -> NoReturn:
        raise failure

    monkeypatch.setattr(handlers, "list_games", failed)

    with pytest.raises(application.InternalError) as captured:
        _games().list(application.Actor("user-id"))

    assert captured.value.__cause__ is failure
    assert str(failure) not in str(captured.value)


def test_public_facade_hides_handler_value_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handler内部のValueErrorを公開入力違反として漏らさない。"""
    failure = ValueError("persisted row contains a private invalid value")

    def invalid(*_args: object, **_kwargs: object) -> NoReturn:
        raise failure

    monkeypatch.setattr(handlers, "list_games", invalid)

    with pytest.raises(application.InternalError) as captured:
        _games().list(application.Actor("user-id"))

    assert captured.value.__cause__ is failure
    assert str(failure) not in str(captured.value)


def test_public_facade_preserves_caller_input_validation() -> None:
    """Facadeが構築する公開queryの入力validationを維持する。"""
    with pytest.raises(ValueError):
        _games().list(application.Actor("user-id"), limit=0)


def test_public_facade_authorizes_before_validating_protected_input() -> None:
    """保護対象操作では入力変換より認可を優先する。"""
    with pytest.raises(application.AppError) as captured:
        _games(policy=_DenyPolicy()).advance(
            "game-id",
            application.Actor("user-id"),
            expected_version=-1,
        )

    assert captured.value.code is application.ErrorCode.AUTHORIZATION_FAILED


def test_public_facade_preserves_owned_game_id_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Applicationが所有するgame ID validation例外を維持する。"""
    failure = InvalidGameIdError("game_id must be a valid UUID")

    def invalid(*_args: object, **_kwargs: object) -> NoReturn:
        raise failure

    monkeypatch.setattr(handlers, "get_game", invalid)

    with pytest.raises(InvalidGameIdError) as captured:
        _games(policy=_AllowPolicy()).get("invalid", application.Actor("user-id"))

    assert captured.value is failure


def test_public_facade_converts_queue_permission_failures() -> None:
    """Queue adapterの認可拒否を安定した公開codeへ変換する。"""
    games = _games(queue=_FailingQueue())

    with pytest.raises(application.AppError) as captured:
        games.operation("operation-id", application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.AUTHORIZATION_FAILED
    assert "private queue detail" not in str(captured.value)


def test_public_facade_converts_missing_operations_to_resource_error() -> None:
    """Queue上に存在しないoperationを公開resource不存在として返す。"""
    games = _games(queue=_MissingQueue())

    with pytest.raises(application.ResourceNotFoundError) as captured:
        games.operation("operation-id", application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.RESOURCE_NOT_FOUND


def test_replay_checks_game_existence_before_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """存在しないゲームのreplay検証をresource不存在として返す。"""

    def missing(*_args: object, **_kwargs: object) -> NoReturn:
        raise GameNotFoundError("private repository detail")

    monkeypatch.setattr(handlers, "get_game", missing)
    games = _games(repository=_ReplayRepository())

    with pytest.raises(application.ResourceNotFoundError):
        games.verify_replay("game-id", application.Actor("admin-id", is_admin=True))


def test_setup_facade_hides_repository_runtime_details() -> None:
    """Setup repositoryの内部失敗を安全な公開失敗へ変換する。"""
    setups = application.SetupApplication(
        cast(Any, object()),
        _config(),
        repository=cast(application.SetupRepository, _FailingSetupRepository()),
    )

    with pytest.raises(application.InternalError) as captured:
        setups.list_setups(application.Actor("user-id"))

    assert captured.value.code is application.ErrorCode.INTERNAL_UNEXPECTED
    assert "private-host" not in str(captured.value)
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_setup_facade_hides_repository_value_errors() -> None:
    """Setup repositoryのValueErrorを公開入力違反として漏らさない。"""
    setups = application.SetupApplication(
        cast(Any, object()),
        _config(),
        repository=cast(application.SetupRepository, _InvalidSetupRepository()),
    )

    with pytest.raises(application.InternalError) as captured:
        setups.list_setups(application.Actor("user-id"))

    assert isinstance(captured.value.__cause__, ValueError)
    assert "persisted setup row" not in str(captured.value)
