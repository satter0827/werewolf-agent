"""Supabase事前確認の純粋処理を検査する。"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from scripts._infra.process import CommandResult
from scripts.supabase import preflight as preflight_supabase
from scripts.supabase.preflight import (
    SupabasePreflight,
    is_supported_supabase_version,
    parse_status_environment,
    select_status_environment,
)

LOCAL_DATABASE_DSN = (
    "postgresql://postgres:local@127.0.0.1:54322/postgres"  # pragma: allowlist secret
)


def test_preflight_import_does_not_load_process_monitor_dependency() -> None:
    """隔離project生成はprocess監視dependencyなしで読み込める。"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            ("import sys; import scripts.supabase.preflight; assert 'psutil' not in sys.modules"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_supabase_cli_version_is_pinned() -> None:
    """Image構成と異なるSupabase CLIで品質実行を開始しない。"""

    assert is_supported_supabase_version("2.104.0\n")
    assert not is_supported_supabase_version("2.105.0\n")


@pytest.mark.parametrize(
    ("missing_executable", "expected_lookups", "expected_message"),
    [
        ("docker", ["docker"], "docker CLIが見つかりません。"),
        ("supabase", ["docker", "supabase"], "supabase CLIが見つかりません。"),
    ],
)
def test_preflight_blocks_before_external_process_when_cli_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    missing_executable: str,
    expected_lookups: list[str],
    expected_message: str,
) -> None:
    """CLI不足は探索順序を保ち、外部process起動前に判定する。"""
    lookups: list[str] = []
    commands: list[list[str]] = []

    def find_executable(command: str) -> str | None:
        lookups.append(command)
        return None if command == missing_executable else command

    monkeypatch.setattr(
        preflight_supabase.shutil,
        "which",
        find_executable,
    )
    monkeypatch.setattr(
        preflight_supabase,
        "run_command",
        lambda command, **_kwargs: commands.append(command),
    )

    with pytest.raises(preflight_supabase.EnvironmentBlockedError) as captured:
        preflight_supabase.prepare_supabase(base_environment={})

    assert str(captured.value) == expected_message
    assert lookups == expected_lookups
    assert commands == []


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
            f'DB_URL="{LOCAL_DATABASE_DSN}"',
        ]
    )

    assert parse_status_environment(output) == {
        "API_URL": "http://127.0.0.1:54321",
        "PUBLISHABLE_KEY": "local-key",
        "SERVICE_ROLE_KEY": "must-not-leak",
        "DB_URL": LOCAL_DATABASE_DSN,
    }
    assert select_status_environment(output) == {
        "API_URL": "http://127.0.0.1:54321",
        "PUBLISHABLE_KEY": "local-key",
        "DB_URL": LOCAL_DATABASE_DSN,
    }


def test_connection_verification_probes_data_api_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        preflight_supabase,
        "_probe_data_api",
        lambda url, _key, **_kwargs: probes.append(("api", url)),
    )
    monkeypatch.setattr(
        preflight_supabase,
        "_probe_database",
        lambda dsn, **_kwargs: probes.append(("database", dsn)),
    )

    preflight_supabase.verify_supabase_connection(
        {
            "WEREWOLF_SUPABASE_URL": "http://127.0.0.1:54321/",
            "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "local-key",
            "WEREWOLF_SUPABASE_DB_DSN": "postgresql://local-dsn",
        }
    )

    assert probes == [
        ("api", "http://127.0.0.1:54321"),
        ("database", "postgresql://local-dsn"),
    ]


def test_platform_schema_drift_is_blocked_without_connection_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight_supabase,
        "_platform_schema_state",
        lambda *_args, **_kwargs: (False, True),
    )
    monotonic_values = iter((0.0, 1.0))
    monkeypatch.setattr(preflight_supabase.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(preflight_supabase.time, "sleep", lambda _seconds: None)

    with pytest.raises(preflight_supabase.EnvironmentBlockedError) as captured:
        preflight_supabase.verify_supabase_platform_schema(
            {"WEREWOLF_SUPABASE_DB_DSN": "postgresql://secret-value"},
            timeout_seconds=1,
        )

    message = str(captured.value)
    assert "auth.jwt()" in message
    assert "backup" in message
    assert "secret-value" not in message


def test_platform_schema_waits_for_supabase_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(((False, True), (True, True)))
    monkeypatch.setattr(
        preflight_supabase,
        "_platform_schema_state",
        lambda *_args, **_kwargs: next(states),
    )
    monkeypatch.setattr(preflight_supabase.time, "sleep", lambda _seconds: None)

    preflight_supabase.verify_supabase_platform_schema(
        {"WEREWOLF_SUPABASE_DB_DSN": "postgresql://local"},
        timeout_seconds=1,
    )


def test_runtime_settings_mismatch_reports_names_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import werewolf_agent.settings as settings_module

    fake_settings = type(
        "FakeSettings",
        (),
        {
            "supabase_url": "http://stale.invalid",
            "supabase_publishable_key_value": "stale-secret-key",
            "supabase_api_db_dsn_value": "postgresql://stale-api-secret-dsn",
            "supabase_worker_db_dsn_value": "postgresql://stale-worker-secret-dsn",
        },
    )()
    monkeypatch.setattr(settings_module, "AppSettings", lambda: fake_settings)

    with pytest.raises(preflight_supabase.EnvironmentBlockedError) as captured:
        preflight_supabase.verify_runtime_settings_connection(
            {
                "WEREWOLF_SUPABASE_URL": "http://127.0.0.1:54321",
                "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "expected-key",
                "WEREWOLF_SUPABASE_API_DB_DSN": "postgresql://expected-api-dsn",
                "WEREWOLF_SUPABASE_WORKER_DB_DSN": "postgresql://expected-worker-dsn",
            }
        )

    message = str(captured.value)
    assert all(name in message for name in preflight_supabase._RUNTIME_CONNECTION_KEYS)
    assert "stale-secret" not in message
    assert "expected-" not in message


def test_runtime_settings_validation_error_never_reports_input_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import BaseModel, ValidationError

    import werewolf_agent.settings as settings_module

    class InvalidSettings(BaseModel):
        supabase_publishable_key: int

    with pytest.raises(ValidationError) as captured_validation:
        InvalidSettings(supabase_publishable_key="secret-input")  # type: ignore[arg-type]
    validation_error = captured_validation.value

    def invalid_settings() -> object:
        raise validation_error

    monkeypatch.setattr(settings_module, "AppSettings", invalid_settings)

    with pytest.raises(preflight_supabase.EnvironmentBlockedError) as captured:
        preflight_supabase.verify_runtime_settings_connection({})

    message = str(captured.value)
    assert "supabase_publishable_key" in message
    assert "secret-input" not in message


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


def test_preflight_blocks_when_dotenv_connection_does_not_match_local_supabase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase.shutil, "which", lambda command: command)
    verified_connections = 0

    def verify_connection(*_args: object, **_kwargs: object) -> None:
        nonlocal verified_connections
        verified_connections += 1

    monkeypatch.setattr(preflight_supabase, "verify_supabase_connection", verify_connection)
    monkeypatch.setattr(
        preflight_supabase, "verify_supabase_platform_schema", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        preflight_supabase,
        "verify_runtime_settings_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            preflight_supabase.EnvironmentBlockedError(
                "runtime接続設定がローカルSupabaseと一致しません: WEREWOLF_SUPABASE_URL"
            )
        ),
    )

    def fake_run(command: list[str], **_kwargs: object) -> CommandResult:
        if command == ["supabase", "--version"]:
            return CommandResult(command, 0, 0.0, "2.104.0\n")
        if command == ["docker", "info"]:
            return CommandResult(command, 0, 0.0, "ready")
        if command[:2] == ["supabase", "status"]:
            return CommandResult(
                command,
                0,
                0.0,
                'API_URL="http://127.0.0.1:54321"\n'
                'PUBLISHABLE_KEY="local-key"\n'
                f'DB_URL="{LOCAL_DATABASE_DSN}"\n',
            )
        if command[:3] == ["supabase", "migration", "up"]:
            return CommandResult(command, 0, 0.0, "migrated")
        raise AssertionError(command)

    monkeypatch.setattr(preflight_supabase, "run_command", fake_run)

    with pytest.raises(
        preflight_supabase.EnvironmentBlockedError,
        match=r"\.envとsettings modelの接続確認",
    ):
        preflight_supabase.prepare_supabase(base_environment={})

    assert verified_connections == 1


def test_isolated_quality_preflight_does_not_use_repository_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    isolated_root = artifact_root / "runtime" / "supabase" / "quality"
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase.shutil, "which", lambda command: command)
    monkeypatch.setattr(
        preflight_supabase,
        "prepare_isolated_project",
        lambda _root: (isolated_root, "werewolf-agent-quality-test"),
    )
    verified_connections = 0

    def verify_connection(*_args: object, **_kwargs: object) -> None:
        nonlocal verified_connections
        verified_connections += 1

    monkeypatch.setattr(preflight_supabase, "verify_supabase_connection", verify_connection)
    monkeypatch.setattr(
        preflight_supabase, "verify_supabase_platform_schema", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        preflight_supabase,
        "verify_runtime_settings_connection",
        lambda *_args, **_kwargs: pytest.fail("品質用projectはrepository設定を読まない"),
    )

    def fake_run(command: list[str], **_kwargs: object) -> CommandResult:
        if command == ["supabase", "--version"]:
            return CommandResult(command, 0, 0.0, "2.104.0\n")
        if command == ["docker", "info"]:
            return CommandResult(command, 0, 0.0, "ready")
        if command[:2] == ["supabase", "status"]:
            return CommandResult(
                command,
                0,
                0.0,
                'API_URL="http://127.0.0.1:54321"\n'
                'PUBLISHABLE_KEY="local-key"\n'
                f'DB_URL="{LOCAL_DATABASE_DSN}"\n',
            )
        if command[:3] == ["supabase", "migration", "up"]:
            return CommandResult(command, 0, 0.0, "migrated")
        raise AssertionError(command)

    monkeypatch.setattr(preflight_supabase, "run_command", fake_run)

    prepared = preflight_supabase.prepare_supabase(isolated_root=isolated_root)

    assert prepared.project_id == "werewolf-agent-quality-test"
    assert verified_connections == 1


def test_supervisor_rejects_second_lifetime_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight_supabase,
        "exclusive_file_lock",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            preflight_supabase.LockTimeoutError(Path("session.lock"))
        ),
    )
    monkeypatch.setattr(
        preflight_supabase,
        "prepare_supabase",
        lambda **_kwargs: pytest.fail("二重ownerは準備を開始してはいけません。"),
    )

    assert preflight_supabase.serve_supabase() == 2


def test_stop_preserves_project_failure_and_still_removes_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / ".werewolf-agent" / "runtime" / "supabase-home" / "run"
    profile.mkdir(parents=True)
    removed: list[Path] = []
    monkeypatch.setattr(
        preflight_supabase,
        "_stop_owned_project",
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


def test_development_stop_preserves_local_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    commands: list[list[str]] = []
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(
        preflight_supabase,
        "run_command",
        lambda command, **_kwargs: (commands.append(command) or CommandResult(command, 0, 0.0, "")),
    )

    preflight_supabase._stop_owned_project(repository_root, "development", {})

    assert commands == [
        [
            "supabase",
            "stop",
            "--project-id",
            "development",
            "--workdir",
            str(repository_root),
        ]
    ]
    assert repository_root.exists()


def test_quality_stop_deletes_only_managed_isolated_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    workdir = artifact_root / "runtime" / "supabase" / "quality"
    workdir.mkdir(parents=True)
    commands: list[list[str]] = []
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr("scripts._infra.process.ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(
        preflight_supabase,
        "run_command",
        lambda command, **_kwargs: (commands.append(command) or CommandResult(command, 0, 0.0, "")),
    )

    preflight_supabase._stop_owned_project(workdir, "werewolf-agent-quality-run", {})

    assert "--no-backup" in commands[0]
    assert not workdir.exists()


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
    ownership: list[bool] = []

    with pytest.raises(preflight_supabase.SupabaseOperationError) as captured:
        preflight_supabase.prepare_supabase(
            isolated_root=workdir,
            ownership_callback=ownership.append,
        )

    assert "start failed" in str(captured.value)
    assert "cleanup failed" in str(captured.value)
    assert ownership == [True]


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
    old = preflight_supabase.time.time() - 60
    preflight_supabase.os.utime(path, (old, old))

    assert preflight_supabase.wait_for_supervisor(timeout_seconds=1) == expected


def test_wait_for_supervisor_rejects_expired_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    path = artifact_root / "runtime" / "supabase" / "supervisor-state.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"run_id": "run", "state": "reserved", "pid": 1234}),
        encoding="utf-8",
    )
    old = preflight_supabase.time.time() - preflight_supabase.SESSION_RESERVATION_SECONDS - 1
    preflight_supabase.os.utime(path, (old, old))
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)

    assert preflight_supabase.wait_for_supervisor(timeout_seconds=1) == 1


def test_development_session_reservation_rejects_active_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase, "_api_port_is_available", lambda: True)

    assert preflight_supabase.reserve_development_session("backend") == 0
    assert preflight_supabase.reserve_development_session("api") == 2

    state = json.loads(preflight_supabase._supervisor_state_path().read_text(encoding="utf-8"))
    assert state["state"] == "reserved"
    assert state["session"] == "backend"
    assert state["pid"] > 0
    assert "environment" not in state


def test_development_session_lock_contention_is_a_clear_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight_supabase,
        "exclusive_file_lock",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            preflight_supabase.LockTimeoutError(Path("session.lock"))
        ),
    )

    assert preflight_supabase.reserve_development_session("backend") == 2


def test_development_session_reclaims_stale_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase, "_api_port_is_available", lambda: True)
    path = preflight_supabase._supervisor_state_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"run_id": "old", "state": "reserved", "pid": 0, "session": "api"}),
        encoding="utf-8",
    )
    old = preflight_supabase.time.time() - preflight_supabase.SESSION_RESERVATION_SECONDS - 1
    preflight_supabase.os.utime(path, (old, old))

    assert preflight_supabase.reserve_development_session("worker") == 0
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["session"] == "worker"


def test_supervisor_state_preserves_session_start_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", tmp_path / ".werewolf-agent")

    preflight_supabase._write_supervisor_state("run", "reserved", session="backend")
    reserved = preflight_supabase._read_supervisor_state()
    preflight_supabase._write_supervisor_state(
        "run",
        "ready",
        session="backend",
        started_by_process=True,
    )
    ready = preflight_supabase._read_supervisor_state()

    assert reserved is not None
    assert ready is not None
    assert ready["started_at"] == reserved["started_at"]
    assert ready["pid"] == preflight_supabase.os.getpid()
    assert ready["started_by_process"] is True


@pytest.mark.parametrize("started_by_process", [False, True])
def test_post_debug_cleanup_stops_only_session_owned_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    started_by_process: bool,
) -> None:
    artifact_root = tmp_path / ".werewolf-agent"
    stopped: list[SupabasePreflight] = []
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(preflight_supabase, "_state_is_active", lambda _state: False)
    monkeypatch.setattr(preflight_supabase, "stop_supabase", stopped.append)
    preflight_supabase._write_supervisor_state(
        "run",
        "ready",
        session="backend",
        pid=99999,
        started_by_process=started_by_process,
    )

    assert preflight_supabase.cleanup_development_session() == 0
    assert len(stopped) == 1
    assert stopped[0].started_by_process is started_by_process
    assert stopped[0].workdir == (
        preflight_supabase.REPOSITORY_ROOT if started_by_process else None
    )
    assert stopped[0].supabase_home == (
        artifact_root / "runtime" / "supabase-home" / "preflight-99999"
    )
    assert not preflight_supabase._supervisor_state_path().exists()


def test_missing_supervisor_state_file_is_not_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", tmp_path / ".werewolf-agent")

    assert preflight_supabase._state_is_active({"state": "reserved", "pid": 1}) is False


def test_development_session_checks_api_port_before_reserving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight_supabase, "ARTIFACT_ROOT", tmp_path / ".werewolf-agent")
    monkeypatch.setattr(preflight_supabase, "_api_port_is_available", lambda: False)

    assert preflight_supabase.reserve_development_session("full-stack") == 2
    assert not preflight_supabase._supervisor_state_path().exists()
