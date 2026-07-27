"""安全なtest levelとローカル実行制約を定義する。"""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY",
    str(Path(__file__).resolve().parents[1] / ".werewolf-agent" / "cache" / "hypothesis"),
)

LEVELS = ("quick", "check", "release", "deep")
LEVEL_INDEX = {level: index for index, level in enumerate(LEVELS)}
_REQUIRED_LEVEL_KEY = pytest.StashKey[str]()
_SELECTED_COUNT_KEY = pytest.StashKey[int]()
_GATED_COUNT_KEY = pytest.StashKey[int]()
_REQUIRED_LEVELS_KEY = pytest.StashKey[set[str]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """test levelとdeep確認optionを追加する。"""

    group = parser.getgroup("werewolf quality")
    group.addoption(
        "--test-level",
        choices=LEVELS,
        default="quick",
        help="実行を許可するtest level。既定値はquick。",
    )
    group.addoption(
        "--confirm-deep",
        action="store_true",
        default=False,
        help="deep testの意図的な実行を確認する。",
    )


def pytest_configure(config: pytest.Config) -> None:
    """markerを登録して収集状態を初期化する。"""
    if os.name == "nt":
        _disable_incompatible_pytest_symlink_cleanup()

    for marker, description in (
        ("unit", "外部serviceを使わないunit test"),
        ("integration", "local integration test"),
        ("supabase", "local Supabaseを使うintegration test"),
        ("monkey", "seed固定の状態遷移探索"),
        ("benchmark", "性能退行の検出"),
        ("deep", "明示確認が必要な拡張test"),
        ("serial", "共有資源を使う直列test"),
    ):
        config.addinivalue_line("markers", f"{marker}: {description}")
    if config.getoption("--test-level") == "deep" and not config.getoption("--confirm-deep"):
        raise pytest.UsageError("deepの実行には--confirm-deepが必要です。")
    config.stash[_SELECTED_COUNT_KEY] = 0
    config.stash[_GATED_COUNT_KEY] = 0
    config.stash[_REQUIRED_LEVELS_KEY] = set()


def _disable_incompatible_pytest_symlink_cleanup() -> None:
    """OneDrive上のpytest一時ACLと競合する終了時走査を無効化する。"""
    import _pytest.pathlib
    import _pytest.tmpdir

    def no_cleanup(_path: Path) -> None:
        return None

    _pytest.pathlib.cleanup_dead_symlinks = no_cleanup
    _pytest.tmpdir.cleanup_dead_symlinks = no_cleanup


@pytest.hookimpl(wrapper=True)
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> Iterator[None]:
    """配置からmarkerを補い、選択済みitemへlevel制限を適用する。"""

    for item in items:
        parts = Path(str(item.path)).parts
        if "integration" in parts:
            item.add_marker("integration")
        elif "unit" in parts:
            item.add_marker("unit")
    yield

    selected_level = str(config.getoption("--test-level"))
    gated = 0
    required_levels: set[str] = set()
    for item in items:
        required = required_level(item)
        item.stash[_REQUIRED_LEVEL_KEY] = required
        if LEVEL_INDEX[required] > LEVEL_INDEX[selected_level]:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Selected test requires --test-level={required}.",
                )
            )
            gated += 1
            required_levels.add(required)
    config.stash[_SELECTED_COUNT_KEY] = len(items)
    config.stash[_GATED_COUNT_KEY] = gated
    config.stash[_REQUIRED_LEVELS_KEY] = required_levels


def required_level(item: pytest.Item) -> str:
    """配置とmarkerからitemの最低test levelを返す。"""

    required = "quick"
    parts = Path(str(item.path)).parts
    if "integration" in parts:
        required = "check"
    if item.get_closest_marker("supabase"):
        required = "release"
    if item.get_closest_marker("monkey") or item.get_closest_marker("benchmark"):
        required = max(required, "check", key=LEVEL_INDEX.__getitem__)
    if item.get_closest_marker("deep"):
        required = "deep"
    return required


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """level制限だけで選択testが全てskipされた場合を失敗にする。"""

    config = session.config
    selected = config.stash.get(_SELECTED_COUNT_KEY, 0)
    gated = config.stash.get(_GATED_COUNT_KEY, 0)
    if selected and selected == gated and exitstatus == pytest.ExitCode.OK:
        levels = config.stash.get(_REQUIRED_LEVELS_KEY, set())
        required = min(levels, key=LEVEL_INDEX.__getitem__)
        reporter = config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep("=", f"Selected tests require --test-level={required}.")
        session.exitstatus = pytest.ExitCode.USAGE_ERROR


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """test processからlocalhost以外へのsocket接続を拒否する。"""

    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(instance: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else address
        if str(host).casefold() not in {"127.0.0.1", "::1", "localhost"}:
            raise OSError(f"外部network接続を拒否しました: {host}")
        return original_connect(instance, address)

    def guarded_getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        normalized = host.decode() if isinstance(host, bytes) else host
        if normalized not in {None, "127.0.0.1", "::1", "localhost"}:
            raise OSError(f"外部DNS解決を拒否しました: {normalized}")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    """Create test temp directories without pytest's restrictive Windows ACLs."""
    root = Path(tempfile.gettempdir()) / "werewolf-agent" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{request.node.name[:40]}-{uuid.uuid4().hex}"
    path.mkdir()

    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
