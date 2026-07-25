"""Environment準備commandの契約。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.environment import manager
from scripts.supabase.constants import LOCAL_EXCLUDED_SERVICES_CSV


def test_ensure_skips_prepared_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fingerprintが一致する環境を再同期しない。"""
    monkeypatch.setattr(manager, "_fingerprint", lambda _profile: "same")
    monkeypatch.setattr(manager, "_ready", lambda _profile, _fingerprint: True)
    monkeypatch.setattr(
        manager,
        "setup",
        lambda _profile: pytest.fail("setup must not run"),
    )

    assert manager.ensure("check") is False


def test_setup_allows_dependency_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """依存準備ではregistryとimage取得を禁止しない。"""
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        manager,
        "_run",
        lambda command, **_kwargs: commands.append(tuple(command)),
    )
    monkeypatch.setattr(manager, "_fingerprint", lambda _profile: "fingerprint")
    monkeypatch.setattr(manager, "STATE_ROOT", Path(".werewolf-agent/runtime/environment"))
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Path, "write_text", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(manager.shutil, "which", lambda command: command)

    manager.setup("release")

    flattened = [" ".join(command) for command in commands]
    assert any(command.startswith("uv sync --frozen") for command in flattened)
    assert any(command.startswith("npm ci") for command in flattened)
    assert any(command.startswith("docker compose") for command in flattened)
    assert any(manager.QUALITY_COMPOSE_PROJECT_NAME in command for command in flattened)
    assert all("--offline" not in command for command in flattened)
    assert all("--pull=false" not in command for command in flattened)
    assert any(LOCAL_EXCLUDED_SERVICES_CSV in command for command in flattened)


def test_environment_state_is_repository_local() -> None:
    """準備状態を共有artifact root配下へ保存する。"""
    assert manager.STATE_ROOT == manager.ARTIFACT_ROOT / "runtime" / "environment"


def test_quiet_environment_command_does_not_inherit_terminal_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """秘密値を含み得る準備commandの出力をterminalへ流さない。"""
    observed: dict[str, object] = {}

    def fake_run(_command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(manager.subprocess, "run", fake_run)

    manager._run(("supabase", "start"), quiet=True)

    assert observed["capture_output"] is True
    assert observed["text"] is True
