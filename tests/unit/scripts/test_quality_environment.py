"""再作成可能な依存環境gateの契約を検査する。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts._infra.process import CommandResult
from scripts.quality.gates import environment


def test_environment_gate_checks_frozen_dependencies_and_runtime_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """検査時にlockを変更せずPython、Node.js、両依存環境を確認する。"""
    commands: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        commands.append(command)
        output = "v22.0.0\n" if "--version" in command else ""
        return CommandResult(list(command), 0, 0.0, output)

    monkeypatch.setattr(environment, "run_command", run)
    monkeypatch.setattr(environment.shutil, "which", lambda command: command)
    context = SimpleNamespace(timeout_seconds=60, environment={})

    result = environment.check_environment(context, tmp_path)

    assert result.returncode == 0
    assert commands == [
        ("uv", "sync", "--check", "--frozen", "--all-groups", "--all-extras"),
        ("node", "--version"),
        ("npm", "ls", "--depth=0", "--ignore-scripts"),
    ]


def test_environment_gate_rejects_unsupported_node_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frontend標準と異なるNode.jsを依存同期済みでも受理しない。"""

    def run(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        output = "v20.0.0\n" if "--version" in command else ""
        return CommandResult(list(command), 0, 0.0, output)

    monkeypatch.setattr(environment, "run_command", run)
    monkeypatch.setattr(environment.shutil, "which", lambda command: command)
    context = SimpleNamespace(timeout_seconds=60, environment={})

    result = environment.check_environment(context, tmp_path)

    assert result.returncode == 1
    assert "Node.js 22" in result.output
