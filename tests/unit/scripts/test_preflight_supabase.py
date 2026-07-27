"""Supabase事前確認の純粋処理を検査する。"""

import json
import re
from pathlib import Path

import pytest
from scripts._infra.process import CommandResult
from scripts.supabase import preflight as preflight_supabase
from scripts.supabase.preflight import (
    APPLICATION_PREFLIGHT_ARGUMENTS,
    SupabasePreflight,
    is_supported_supabase_version,
    parse_status_environment,
    select_status_environment,
)


def test_application_preflight_uses_the_current_cli_command() -> None:
    """Supabase preflightが廃止済みのCLI aliasへ戻らない。"""
    assert APPLICATION_PREFLIGHT_ARGUMENTS == ("system", "doctor")


def test_supabase_cli_version_is_pinned() -> None:
    """Image構成と異なるSupabase CLIで品質実行を開始しない。"""

    assert is_supported_supabase_version("2.104.0\n")
    assert not is_supported_supabase_version("2.105.0\n")


@pytest.mark.parametrize("value", ["0", "-1"])
def test_preflight_rejects_non_positive_timeout(value: str) -> None:
    """不正なtimeoutを外部process起動前に拒否する。"""

    with pytest.raises(SystemExit) as captured:
        preflight_supabase.build_parser().parse_args(["--timeout", value])

    assert captured.value.code == 2


def test_parse_status_environment_accepts_only_env_assignments() -> None:
    """CLIの補足文を接続環境へ混入させない。"""

    output = "\n".join(
        [
            'API_URL="http://127.0.0.1:54321"',
            'PUBLISHABLE_KEY="local-key"',
            'SERVICE_ROLE_KEY="must-not-leak"',
            "Stopped services: analytics",
            'DB_URL="postgresql://postgres:local@127.0.0.1:54322/postgres"',
        ]
    )

    assert parse_status_environment(output) == {
        "API_URL": "http://127.0.0.1:54321",
        "PUBLISHABLE_KEY": "local-key",
        "SERVICE_ROLE_KEY": "must-not-leak",
        "DB_URL": "postgresql://postgres:local@127.0.0.1:54322/postgres",
    }
    assert select_status_environment(output) == {
        "API_URL": "http://127.0.0.1:54321",
        "PUBLISHABLE_KEY": "local-key",
        "DB_URL": "postgresql://postgres:local@127.0.0.1:54322/postgres",
    }


def test_isolated_project_uses_distinct_project_id_and_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """品質用Supabaseを開発用projectと同じcontainerへ接続させない。"""

    repository = tmp_path / "repository"
    source = repository / "supabase"
    (source / "migrations").mkdir(parents=True)
    (source / "migrations" / "001.sql").write_text("select 1;\n", encoding="utf-8")
    (source / "config.toml").write_text(
        'project_id = "development"\n[api]\nport = 54321\n[db]\nport = 54322\n',
        encoding="utf-8",
    )
    artifact_root = repository / ".werewolf-agent"
    isolated_root = artifact_root / "db" / "quality" / "run-1"
    monkeypatch.setattr(preflight_supabase, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr("scripts._infra.process.ARTIFACT_ROOT", artifact_root)

    workdir, project_id = preflight_supabase.prepare_isolated_project(isolated_root)

    config = (workdir / "supabase" / "config.toml").read_text(encoding="utf-8")
    ports = [int(port) for port in re.findall(r"^port = (\d+)$", config, re.MULTILINE)]
    assert project_id == preflight_supabase.isolated_project_id(isolated_root)
    assert 'project_id = "development"' not in config
    assert len(ports) == len(set(ports)) == 2
    assert set(ports).isdisjoint({54321, 54322})
    assert (workdir / "supabase" / "migrations" / "001.sql").is_file()

    second_root = artifact_root / "db" / "quality" / "run-2"
    _, second_project_id = preflight_supabase.prepare_isolated_project(second_root)
    assert second_project_id != project_id


def test_stack_supervisor_does_not_stop_unowned_supabase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stack開始前から存在するSupabaseを終了時に停止しない。"""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> CommandResult:
        commands.append(command)
        return CommandResult(command, 0, 0.0, "")

    monkeypatch.setattr(preflight_supabase, "run_command", fake_run)
    artifact_root = tmp_path / ".werewolf-agent"
    profile = artifact_root / "runtime" / "supabase-home" / "run"
    profile.mkdir(parents=True)
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr("scripts._infra.process.ARTIFACT_ROOT", artifact_root)
    prepared = SupabasePreflight(
        environment={},
        started_by_process=False,
        supabase_home=profile,
    )

    preflight_supabase.stop_supabase(prepared)
    assert commands == []
    assert not profile.exists()


def test_status_parse_failure_does_not_stop_preexisting_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    artifact_root = tmp_path / ".werewolf-agent"
    profile = artifact_root / "runtime" / "supabase-home" / "run"
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase.shutil, "which", lambda command: command)

    def fake_run(command: list[str], **_kwargs: object) -> CommandResult:
        commands.append(command)
        if command == ["supabase", "--version"]:
            return CommandResult(command, 0, 0.0, "2.104.0\n")
        if command == ["docker", "info"]:
            return CommandResult(command, 0, 0.0, "ready")
        if command[:2] == ["supabase", "status"]:
            return CommandResult(command, 0, 0.0, "unexpected output")
        return CommandResult(command, 0, 0.0, "")

    monkeypatch.setattr(preflight_supabase, "run_command", fake_run)

    with pytest.raises(preflight_supabase.SupabaseOperationError):
        preflight_supabase.prepare_supabase(
            base_environment={"SUPABASE_HOME": str(profile)},
        )

    assert not any(command[:2] == ["supabase", "stop"] for command in commands)


def test_stop_preserves_project_failure_and_still_removes_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / ".werewolf-agent" / "runtime" / "supabase-home" / "run"
    profile.mkdir(parents=True)
    removed: list[Path] = []
    monkeypatch.setattr(
        preflight_supabase,
        "_stop_isolated_project",
        lambda *_args: CommandResult(["supabase", "stop"], 1, 0.1, "stop failed"),
    )
    monkeypatch.setattr(
        preflight_supabase,
        "_remove_supabase_home",
        lambda path: removed.append(path),
    )
    prepared = SupabasePreflight(
        {},
        True,
        workdir=tmp_path,
        project_id="owned-project",
        supabase_home=profile,
    )

    with pytest.raises(preflight_supabase.SupabaseOperationError, match="stop failed"):
        preflight_supabase.stop_supabase(prepared)

    assert removed == [profile]


def test_start_failure_reports_scoped_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    workdir = artifact_root / "runtime" / "supabase" / "run"
    workdir.mkdir(parents=True)
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase.shutil, "which", lambda command: command)
    monkeypatch.setattr(
        preflight_supabase,
        "prepare_isolated_project",
        lambda _root: (workdir, "owned-project"),
    )

    def fake_run(command: list[str], **_kwargs: object) -> CommandResult:
        if command == ["supabase", "--version"]:
            return CommandResult(command, 0, 0.0, "2.104.0\n")
        if command == ["docker", "info"]:
            return CommandResult(command, 0, 0.0, "ready")
        if command[:2] == ["supabase", "status"]:
            return CommandResult(command, 1, 0.0, "not running")
        if command[:2] == ["supabase", "start"]:
            return CommandResult(command, 1, 0.1, "start failed")
        if command[:2] == ["supabase", "stop"]:
            return CommandResult(command, 1, 0.1, "cleanup failed")
        raise AssertionError(command)

    monkeypatch.setattr(preflight_supabase, "run_command", fake_run)

    with pytest.raises(preflight_supabase.SupabaseOperationError) as captured:
        preflight_supabase.prepare_supabase(isolated_root=workdir)

    assert "start failed" in str(captured.value)
    assert "cleanup failed" in str(captured.value)


def test_finite_preflight_releases_resources_before_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = SupabasePreflight({}, True, workdir=Path("work"), project_id="owned")
    stopped: list[SupabasePreflight] = []
    monkeypatch.setattr(preflight_supabase, "prepare_supabase", lambda **_kwargs: prepared)
    monkeypatch.setattr(preflight_supabase, "stop_supabase", stopped.append)
    monkeypatch.setattr(preflight_supabase, "_publish_supabase_report", lambda *_args: None)

    assert preflight_supabase.main(["--timeout", "1"]) == 0
    assert stopped == [prepared]


def test_wait_for_supervisor_accepts_only_live_ready_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stack利用processは準備を完了した生存中のsupervisorだけを信頼する。"""
    artifact_root = tmp_path / ".werewolf-agent"
    state = artifact_root / "runtime" / "supabase" / "supervisor-state.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps({"run_id": "run", "state": "ready", "pid": 1234}),
        encoding="utf-8",
    )
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase, "_is_live_supervisor", lambda pid: pid == 1234)

    assert preflight_supabase.wait_for_supervisor(timeout_seconds=1) == 0


@pytest.mark.parametrize(("state", "expected"), [("blocked", 2), ("error", 1)])
def test_wait_for_supervisor_propagates_startup_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    expected: int,
) -> None:
    """準備失敗は待機processでもblockedとerrorを区別する。"""
    artifact_root = tmp_path / ".werewolf-agent"
    path = artifact_root / "runtime" / "supabase" / "supervisor-state.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"run_id": "run", "state": state, "pid": 1234, "report": "report.json"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)

    assert preflight_supabase.wait_for_supervisor(timeout_seconds=1) == expected
