"""品質runnerの公開仕様を検査する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts._infra import process as support
from scripts._infra.artifacts import ArtifactLayout
from scripts.quality import retention
from scripts.quality import runner as quality
from scripts.quality.gates import repository, services
from scripts.quality.models import ResourceLease
from scripts.quality.repository import ChangeSet

ROOT = Path(__file__).resolve().parents[3]


def test_cleanup_orphaned_supabase_stops_only_quality_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """containerとvolumeから過去runの品質projectだけを列挙して停止する。"""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> support.CommandResult:
        commands.append(command)
        if command[:2] == ["docker", "ps"]:
            return support.CommandResult(
                command,
                0,
                0.0,
                "development\nwerewolf-agent-quality-old\nwerewolf-agent-quality-old\n",
            )
        if command[:3] == ["docker", "volume", "ls"]:
            return support.CommandResult(
                command,
                0,
                0.0,
                "development\nwerewolf-agent-quality-volume-only\n",
            )
        return support.CommandResult(command, 0, 0.0, "stopped\n")

    monkeypatch.setattr(services, "run_command", fake_run)
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        started_at=quality.utc_now(),
    )

    result = services.cleanup_orphaned_supabase(context, tmp_path)

    assert result.returncode == 0
    assert commands[2] == [
        "supabase",
        "stop",
        "--project-id",
        "werewolf-agent-quality-old",
        "--no-backup",
    ]
    assert commands[3] == [
        "supabase",
        "stop",
        "--project-id",
        "werewolf-agent-quality-volume-only",
        "--no-backup",
    ]
    assert len(commands) == 4


def test_repository_gate_rejects_undefined_artifact_areas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成果物rootへ旧構造や用途不明のlatestを再導入させない。"""
    artifact_root = tmp_path / ".werewolf-agent"
    (artifact_root / "diagnostic-architecture").mkdir(parents=True)
    (artifact_root / "quality" / "manual").mkdir(parents=True)
    monkeypatch.setattr(repository, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(repository, "LAYOUT", ArtifactLayout(artifact_root))
    context = quality.RunContext(
        profile="focus",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path / "run",
        environment={},
        started_at=quality.utc_now(),
    )

    result = repository.check_artifact_placement(context, tmp_path)

    assert result.returncode == 1
    assert "diagnostic-architecture" in result.output
    assert "manual" in result.output


@pytest.mark.parametrize(
    ("base_ref", "head_ref", "expected_tail"),
    [
        (
            "origin/develop",
            "feature-head",
            ["--base-ref", "origin/develop", "--head-ref", "feature-head"],
        ),
        (None, "HEAD", ["--base-ref", "origin/main", "--head-ref", "HEAD"]),
    ],
)
def test_version_gate_uses_the_resolved_quality_change_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base_ref: str | None,
    head_ref: str,
    expected_tail: list[str],
) -> None:
    """Version検査だけが品質実行と異なる差分を再計算しない。"""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> support.CommandResult:
        commands.append(command)
        return support.CommandResult(command, 0, 0.0, "version contract passed\n")

    monkeypatch.setattr(repository, "run_command", fake_run)
    context = quality.RunContext(
        profile="check",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        started_at=quality.utc_now(),
        change=ChangeSet(base_ref, "base", "head", "merge-base", (), head_ref),
    )

    result = repository.check_version_contract(context, tmp_path)

    assert result.returncode == 0
    assert commands[0][-len(expected_tail) :] == expected_tail


def test_execute_stops_owned_supabase_when_runner_is_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gate間の割り込みでも品質所有Supabaseのcleanupを実行する。"""

    for relative in ("logs", "test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    settings = quality.load_quality_settings()
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        retention,
        "publish_run",
        lambda run_dir, _selector, _state: run_dir / "report.json",
    )
    stages = [[quality.Gate("start", "start")], [quality.Gate("interrupt", "interrupt")]]
    stopped = False

    def run_gate(context: quality.RunContext, gate: quality.Gate) -> quality.GateResult:
        nonlocal stopped
        if gate.name == "start":
            context.resources["supabase"] = ResourceLease("supabase", cleanup_required=True)
        elif gate.name == "interrupt":
            raise KeyboardInterrupt
        elif gate.name == "supabase-stop":
            stopped = True
        return quality.GateResult(gate.name, gate.description, "passed", 0.0)

    monkeypatch.setattr(quality, "create_run_directory", lambda _profile: ("run", tmp_path))
    monkeypatch.setattr(quality, "quality_environment", lambda **_kwargs: {})
    monkeypatch.setattr(quality, "_profile_stages", lambda *_args, **_kwargs: stages)
    monkeypatch.setattr(quality, "_run_gate", run_gate)

    state, report_path = quality.execute(
        "release",
        jobs=1,
        timeout_seconds=1,
        settings=settings,
    )

    assert state == "error"
    assert stopped is True
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "error"
    assert any(result["name"] == "runner" for result in report["results"])
    assert any(result["state"] == "skipped" for result in report["results"])


def test_supabase_cleanup_removes_isolated_cli_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """projectが既に停止済みでもrun固有SUPABASE_HOMEを削除する。"""

    artifact_root = tmp_path / ".werewolf-agent"
    profile = artifact_root / "runtime" / "supabase-home" / "run"
    profile.mkdir(parents=True)
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={"SUPABASE_HOME": str(profile)},
        started_at=quality.utc_now(),
        resources={
            "supabase": ResourceLease(
                "supabase",
                cleanup_required=True,
                workdir=tmp_path / "missing-project",
                identifier="quality-project",
            )
        },
    )
    monkeypatch.setattr(support, "ARTIFACT_ROOT", artifact_root)

    result = services.stop_supabase(context, tmp_path / "log")

    assert result.returncode == 0
    assert not profile.exists()


def test_supabase_cleanup_failure_keeps_lease_for_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / ".werewolf-agent" / "runtime" / "supabase" / "run"
    workdir.mkdir(parents=True)
    lease = ResourceLease(
        "supabase",
        cleanup_required=True,
        workdir=workdir,
        identifier="werewolf-agent-quality-run",
    )
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        started_at=quality.utc_now(),
        resources={"supabase": lease},
    )
    monkeypatch.setattr(
        services,
        "run_command",
        lambda command, **_kwargs: support.CommandResult(command, 1, 0.0, "stop failed"),
    )

    result = services.stop_supabase(context, tmp_path / "log")

    assert result.returncode == 1
    assert lease.cleanup_required is True
    assert lease.identifier == "werewolf-agent-quality-run"
    assert lease.workdir == workdir


def test_supabase_ownership_is_recorded_before_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight割り込み前にcleanupに必要な所有情報を確定する。"""

    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        started_at=quality.utc_now(),
    )
    monkeypatch.setattr(services, "LAYOUT", ArtifactLayout(tmp_path / ".werewolf-agent"))
    monkeypatch.setattr(
        services,
        "prepare_supabase",
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        services.start_supabase(context, tmp_path / "log")

    lease = context.resources["supabase"]
    assert lease.cleanup_required is True
    assert lease.workdir is not None
    assert lease.identifier == services.isolated_project_id(lease.workdir)


def test_blocked_supabase_preflight_releases_local_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker未起動時に停止処理を重ねずblockedだけを報告する。"""
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        started_at=quality.utc_now(),
    )
    monkeypatch.setattr(services, "LAYOUT", ArtifactLayout(tmp_path / ".werewolf-agent"))
    monkeypatch.setattr(
        services,
        "prepare_supabase",
        lambda **_kwargs: (_ for _ in ()).throw(
            quality.EnvironmentBlockedError("Docker engineが起動していません。")
        ),
    )

    with pytest.raises(quality.EnvironmentBlockedError):
        services.start_supabase(context, tmp_path / "log")

    lease = context.resources["supabase"]
    assert lease.cleanup_required is False
    assert lease.workdir is None
    assert lease.identifier is None


def test_supabase_lint_uses_the_owned_local_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """schema lintを品質run固有workdirへ限定する。"""
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=120,
        run_id="run",
        run_dir=tmp_path,
        environment={"QUALITY": "1"},
        started_at=quality.utc_now(),
    )
    context.resources["supabase"] = ResourceLease("supabase", workdir=tmp_path / "project")
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> quality.CommandResult:
        captured["command"] = command
        captured["environment"] = kwargs["environment"]
        return quality.CommandResult(command, 0, 0.0, "No schema errors found")

    monkeypatch.setattr(services, "run_command", run)

    result = services.lint_supabase(context, tmp_path)

    assert result.returncode == 0
    assert captured["command"] == [
        "supabase",
        "db",
        "lint",
        "--local",
        "--fail-on",
        "error",
        "--workdir",
        str(tmp_path / "project"),
    ]
    assert captured["environment"] == context.environment
