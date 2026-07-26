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

ROOT = Path(__file__).resolve().parents[3]


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
    monkeypatch.setattr(repository, "git_status", lambda _environment: "")
    monkeypatch.setattr(quality, "_profile_stages", lambda *_args: stages)
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

    temporary_root = tmp_path / "temporary" / "werewolf-agent"
    profile = temporary_root / "supabase" / "run"
    profile.mkdir(parents=True)
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={"SUPABASE_HOME": str(profile)},
        initial_git_status="",
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
    monkeypatch.setattr(support, "TEMPORARY_ROOT", temporary_root)

    result = services.stop_supabase(context, tmp_path / "log")

    assert result.returncode == 0
    assert not profile.exists()


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
        initial_git_status="",
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
        initial_git_status="",
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
