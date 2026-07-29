"""再作成可能な依存環境gateの契約を検査する。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts._infra.process import CommandResult
from scripts.quality import runner
from scripts.quality.gates import environment


def test_environment_gate_checks_frozen_python_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """検査時にlockを変更せずPython依存環境を確認する。"""
    commands: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        commands.append(command)
        return CommandResult(list(command), 0, 0.0, "")

    monkeypatch.setattr(environment, "run_command", run)
    monkeypatch.setattr(
        environment,
        "inspect_environment",
        lambda _profile: SimpleNamespace(state="passed", confirmed_causes=[]),
    )
    context = SimpleNamespace(
        timeout_seconds=60,
        environment={},
        profile="check",
        environment_target="python",
    )

    result = environment.check_environment(context, tmp_path)

    assert result.returncode == 0
    assert commands == [(environment.sys.executable, "-c", "import werewolf_agent")]


def test_runner_rejects_dependency_environment_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """品質実行前後のinstalled distribution差分を失敗にする。"""
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    context = SimpleNamespace(
        initial_dependency_fingerprint="before",
        run_dir=run_dir,
    )
    monkeypatch.setattr(runner, "python_installation_fingerprint", lambda: "after")

    result = runner._environment_stability_result(context)

    assert result.state == "failed"
    assert result.returncode == 1
    assert "変更されました" in (result.message or "")


def test_environment_gate_distinguishes_blocked_from_inspection_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = SimpleNamespace(
        timeout_seconds=60,
        environment={},
        profile="check",
        environment_target="python",
    )
    monkeypatch.setattr(
        environment,
        "inspect_environment",
        lambda _profile: SimpleNamespace(state="blocked", confirmed_causes=["未準備"]),
    )
    blocked = environment.check_environment(context, tmp_path)
    assert blocked.returncode == 2

    monkeypatch.setattr(
        environment,
        "inspect_environment",
        lambda _profile: SimpleNamespace(state="error", confirmed_causes=["検査基盤失敗"]),
    )
    reported_error = environment.check_environment(context, tmp_path)
    assert reported_error.returncode == 1

    monkeypatch.setattr(
        environment,
        "inspect_environment",
        lambda _profile: (_ for _ in ()).throw(OSError("broken")),
    )
    error = environment.check_environment(context, tmp_path)
    assert error.returncode == 1
