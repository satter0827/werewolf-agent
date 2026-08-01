"""ローカルSupabaseをrelease検証に使える状態へ整える。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts._infra.locking import LockTimeoutError, exclusive_file_lock
from scripts._infra.operations import operation_run_id, publish_operation
from scripts._infra.process import (
    ARTIFACT_ROOT,
    REPOSITORY_ROOT,
    CommandResult,
    EnvironmentBlockedError,
    quality_environment,
    redact,
    remove_managed_path,
    run_command,
    utc_now,
    write_json,
)
from scripts.supabase.constants import LOCAL_EXCLUDED_SERVICES_CSV, SUPPORTED_CLI_VERSION

_ENV_LINE = re.compile(r'^([A-Z][A-Z0-9_]*)="?(.*?)"?$')
_ALLOWED_STATUS_KEYS = frozenset({"ANON_KEY", "API_URL", "DB_URL", "PUBLISHABLE_KEY"})
_RUNTIME_CONNECTION_KEYS = (
    "WEREWOLF_SUPABASE_URL",
    "WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    "WEREWOLF_SUPABASE_API_DB_DSN",
    "WEREWOLF_SUPABASE_WORKER_DB_DSN",
)
_CONNECTION_PROBE_KEYS = (
    "WEREWOLF_SUPABASE_URL",
    "WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    "WEREWOLF_SUPABASE_DB_DSN",
)
SUPERVISOR_STATE_FILE = "supervisor-state.json"
SESSION_LOCK_FILE = "development-session.lock"
SESSION_RESERVATION_SECONDS = 15


class SupabaseOperationError(RuntimeError):
    """前提確認後に発生したSupabase操作失敗。"""


def is_supported_supabase_version(output: str) -> bool:
    """Supabase CLIが品質基盤で固定した版か判定する。"""
    return output.strip() == SUPPORTED_CLI_VERSION


def isolated_project_id(isolated_root: Path) -> str:
    """品質用workdirから再現可能で衝突しないproject IDを返す。"""
    identity = hashlib.sha256(str(isolated_root.resolve()).encode()).hexdigest()[:12]
    return f"werewolf-agent-quality-{identity}"


@dataclass(frozen=True, slots=True)
class SupabasePreflight:
    """Supabase事前確認の結果。"""

    environment: dict[str, str]
    started_by_process: bool
    workdir: Path | None = None
    project_id: str | None = None
    supabase_home: Path | None = None


def parse_status_environment(output: str) -> dict[str, str]:
    """`supabase status -o env`の出力を環境変数へ変換する。"""
    environment: dict[str, str] = {}
    for raw_line in output.splitlines():
        match = _ENV_LINE.fullmatch(raw_line.strip())
        if match:
            environment[match.group(1)] = match.group(2)
    return environment


def select_status_environment(output: str) -> dict[str, str]:
    """品質実行に必要なSupabase接続値だけを返す。"""
    return {
        key: value
        for key, value in parse_status_environment(output).items()
        if key in _ALLOWED_STATUS_KEYS
    }


def verify_supabase_connection(
    environment: Mapping[str, str],
    *,
    timeout_seconds: int = 10,
) -> None:
    """Data APIとPostgreSQLへ接続し、CLI由来の接続情報を実証する。"""
    url = environment.get("WEREWOLF_SUPABASE_URL", "").strip().rstrip("/")
    key = environment.get("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", "").strip()
    dsn = environment.get("WEREWOLF_SUPABASE_DB_DSN", "").strip()
    missing = [
        name
        for name, value in zip(_CONNECTION_PROBE_KEYS, (url, key, dsn), strict=True)
        if not value
    ]
    if missing:
        raise SupabaseOperationError("Supabase接続情報が不足しています: " + ", ".join(missing))
    timeout = max(1, min(timeout_seconds, 30))
    _probe_data_api(url, key, timeout_seconds=timeout)
    _probe_database(dsn, timeout_seconds=timeout)


def verify_runtime_settings_connection(
    expected_environment: Mapping[str, str],
    *,
    timeout_seconds: int = 10,
) -> None:
    """実プロセスと同じsettings sourceで接続先一致と到達性を確認する。"""
    from pydantic import ValidationError

    from werewolf_agent.settings import AppSettings

    try:
        settings = AppSettings()  # type: ignore[call-arg]
    except ValidationError as error:
        fields = sorted(
            {
                str(item["loc"][0])
                for item in error.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                )
                if item.get("loc")
            }
        )
        suffix = f": {', '.join(fields)}" if fields else ""
        raise EnvironmentBlockedError(
            f"runtime settingsを検証できません。設定名を確認してください{suffix}"
        ) from error
    runtime_environment = {
        "WEREWOLF_SUPABASE_URL": settings.supabase_url,
        "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": settings.supabase_publishable_key_value,
        "WEREWOLF_SUPABASE_API_DB_DSN": settings.supabase_api_db_dsn_value,
        "WEREWOLF_SUPABASE_WORKER_DB_DSN": settings.supabase_worker_db_dsn_value,
    }
    mismatched = [
        name
        for name in _RUNTIME_CONNECTION_KEYS
        if _normalized_connection_value(name, runtime_environment[name])
        != _normalized_connection_value(name, expected_environment.get(name, ""))
    ]
    if mismatched:
        raise EnvironmentBlockedError(
            "runtime接続設定がローカルSupabaseと一致しません: " + ", ".join(mismatched)
        )
    try:
        verify_supabase_connection(
            {
                **runtime_environment,
                "WEREWOLF_SUPABASE_DB_DSN": settings.supabase_api_db_dsn_value,
            },
            timeout_seconds=timeout_seconds,
        )
    except SupabaseOperationError as error:
        raise EnvironmentBlockedError(
            "runtime接続設定でローカルSupabaseへ接続できません: "
            + ", ".join(_RUNTIME_CONNECTION_KEYS)
        ) from error


def _normalized_connection_value(name: str, value: str) -> str:
    return value.strip().rstrip("/") if name == "WEREWOLF_SUPABASE_URL" else value.strip()


def _probe_data_api(url: str, key: str, *, timeout_seconds: int) -> None:
    import httpx

    try:
        response = httpx.get(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SupabaseOperationError("Supabase Data APIへ接続できませんでした。") from error


def _probe_database(dsn: str, *, timeout_seconds: int) -> None:
    import psycopg

    try:
        with psycopg.connect(dsn, connect_timeout=timeout_seconds) as connection:
            connection.execute("select 1").fetchone()
    except psycopg.Error as error:
        raise SupabaseOperationError("Supabase PostgreSQLへ接続できませんでした。") from error


def verify_supabase_platform_schema(
    environment: Mapping[str, str],
    *,
    timeout_seconds: int = 10,
) -> None:
    """Application migrationが前提にするSupabase管理schemaを確認する。"""
    dsn = environment.get("WEREWOLF_SUPABASE_DB_DSN", "").strip()
    if not dsn:
        raise SupabaseOperationError("Supabase接続情報が不足しています: WEREWOLF_SUPABASE_DB_DSN")
    timeout = max(1, min(timeout_seconds, 30))
    deadline = time.monotonic() + timeout
    while True:
        jwt_function, users_table = _platform_schema_state(
            dsn,
            timeout_seconds=timeout,
        )
        if jwt_function and users_table:
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(0.25)
    missing = []
    if not jwt_function:
        missing.append("auth.jwt()")
    if not users_table:
        missing.append("auth.users")
    if missing:
        raise EnvironmentBlockedError(
            "ローカルSupabase基盤が固定CLI版と互換ではありません。"
            f"不足: {', '.join(missing)}。"
            "必要な開発データをbackupしてからlocal projectを明示的に再作成してください。"
        )


def _platform_schema_state(dsn: str, *, timeout_seconds: int) -> tuple[bool, bool]:
    import psycopg

    try:
        with psycopg.connect(dsn, connect_timeout=timeout_seconds) as connection:
            row = connection.execute(
                "select to_regprocedure('auth.jwt()') is not null, "
                "to_regclass('auth.users') is not null"
            ).fetchone()
    except psycopg.Error as error:
        raise SupabaseOperationError("Supabase管理schemaを確認できませんでした。") from error
    if row is None:
        raise SupabaseOperationError("Supabase管理schemaの確認結果を取得できませんでした。")
    return bool(row[0]), bool(row[1])


def prepare_supabase(
    *,
    timeout_seconds: int = 180,
    isolated_root: Path | None = None,
    base_environment: Mapping[str, str] | None = None,
    ownership_callback: Callable[[bool], None] | None = None,
) -> SupabasePreflight:
    """Supabaseを起動してmigrationとアプリ側の事前確認を行う。"""
    for executable in ("docker", "supabase"):
        if shutil.which(executable) is None:
            raise EnvironmentBlockedError(f"{executable} CLIが見つかりません。")

    environment = dict(base_environment) if base_environment is not None else quality_environment()
    environment["SUPABASE_HOME"] = str(
        ARTIFACT_ROOT / "runtime" / "supabase-home" / f"preflight-{os.getpid()}"
    )
    environment["SUPABASE_TELEMETRY_DISABLED"] = "true"
    supabase_home = Path(environment["SUPABASE_HOME"])
    version = run_command(
        ["supabase", "--version"],
        timeout_seconds=30,
        environment=environment,
    )
    if version.returncode != 0 or not is_supported_supabase_version(version.output):
        detected = version.output.strip() or "不明"
        _remove_supabase_home(supabase_home)
        raise EnvironmentBlockedError(
            f"Supabase CLIの版が一致しません。必要: {SUPPORTED_CLI_VERSION}、検出: {detected}"
        )
    try:
        workdir = REPOSITORY_ROOT
        project_id = configured_project_id(workdir)
        if isolated_root is not None:
            workdir, project_id = prepare_isolated_project(isolated_root)
    except Exception:
        _remove_supabase_home(supabase_home)
        raise
    docker = run_command(
        ["docker", "info"],
        timeout_seconds=30,
        environment=environment,
    )
    if docker.returncode != 0:
        _remove_supabase_home(supabase_home)
        raise EnvironmentBlockedError("Docker engineが起動していません。")
    status = run_command(
        _supabase_command(["status", "-o", "env"], workdir),
        timeout_seconds=30,
        environment=environment,
    )
    started_by_process = False
    if status.returncode != 0:
        if ownership_callback is not None:
            ownership_callback(True)
        started = run_command(
            _supabase_command(
                [
                    "start",
                    "--exclude",
                    LOCAL_EXCLUDED_SERVICES_CSV,
                ],
                workdir,
            ),
            timeout_seconds=timeout_seconds,
            environment=environment,
        )
        if started.returncode != 0:
            cleanup = _cleanup_preflight_resources(
                workdir,
                project_id,
                environment,
                supabase_home,
                stop_project=True,
            )
            raise SupabaseOperationError(
                _with_cleanup_failure(
                    _failure_message("ローカルSupabaseを起動できませんでした。", started),
                    cleanup,
                )
            )
        started_by_process = True
        status = run_command(
            _supabase_command(["status", "-o", "env"], workdir),
            timeout_seconds=30,
            environment=environment,
        )
    elif ownership_callback is not None:
        ownership_callback(False)
    local_environment = select_status_environment(status.output)
    if not local_environment:
        cleanup = _cleanup_preflight_resources(
            workdir,
            project_id,
            environment,
            supabase_home,
            stop_project=started_by_process,
        )
        raise SupabaseOperationError(
            _with_cleanup_failure("Supabaseのローカル接続情報を取得できませんでした。", cleanup)
        )
    local_environment.update(
        {
            "WEREWOLF_SUPABASE_URL": local_environment.get("API_URL", ""),
            "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": local_environment.get(
                "PUBLISHABLE_KEY", local_environment.get("ANON_KEY", "")
            ),
            "WEREWOLF_SUPABASE_DB_DSN": local_environment.get("DB_URL", ""),
            "WEREWOLF_SUPABASE_API_DB_DSN": local_environment.get("DB_URL", ""),
            "WEREWOLF_SUPABASE_WORKER_DB_DSN": local_environment.get("DB_URL", ""),
        }
    )

    child_extra = dict(local_environment)
    if isolated_root is not None:
        profile = isolated_root / "profile"
        child_extra.update(
            {
                "APPDATA": str(profile),
                "LOCALAPPDATA": str(profile),
                "XDG_CONFIG_HOME": str(profile),
            }
        )
    child_environment = quality_environment(extra=child_extra)
    try:
        verify_supabase_platform_schema(
            local_environment,
            timeout_seconds=min(timeout_seconds, 30),
        )
    except (EnvironmentBlockedError, SupabaseOperationError) as error:
        cleanup = _cleanup_preflight_resources(
            workdir,
            project_id,
            environment,
            supabase_home,
            stop_project=started_by_process,
        )
        message = _with_cleanup_failure(str(error), cleanup)
        if isinstance(error, EnvironmentBlockedError):
            raise EnvironmentBlockedError(message) from error
        raise SupabaseOperationError(message) from error
    migration = run_command(
        _supabase_command(["migration", "up", "--local"], workdir),
        timeout_seconds=timeout_seconds,
        environment=child_environment,
    )
    if migration.returncode != 0:
        cleanup = _cleanup_preflight_resources(
            workdir,
            project_id,
            environment,
            supabase_home,
            stop_project=started_by_process,
        )
        raise SupabaseOperationError(
            _with_cleanup_failure(
                _failure_message("Supabase migrationの適用に失敗しました。", migration),
                cleanup,
            )
        )

    try:
        verify_supabase_connection(local_environment, timeout_seconds=min(timeout_seconds, 30))
    except SupabaseOperationError as error:
        cleanup = _cleanup_preflight_resources(
            workdir,
            project_id,
            environment,
            supabase_home,
            stop_project=started_by_process,
        )
        raise SupabaseOperationError(
            _with_cleanup_failure(
                str(error),
                cleanup,
            )
        ) from error
    try:
        if isolated_root is None:
            verify_runtime_settings_connection(
                local_environment,
                timeout_seconds=min(timeout_seconds, 30),
            )
    except (EnvironmentBlockedError, ValueError) as error:
        cleanup = _cleanup_preflight_resources(
            workdir,
            project_id,
            environment,
            supabase_home,
            stop_project=started_by_process,
        )
        raise EnvironmentBlockedError(
            _with_cleanup_failure(
                f".envとsettings modelの接続確認に失敗しました。{error}",
                cleanup,
            )
        ) from error
    local_environment.update(
        {
            "SUPABASE_HOME": str(supabase_home),
            "SUPABASE_TELEMETRY_DISABLED": "true",
        }
    )
    return SupabasePreflight(
        local_environment,
        started_by_process,
        workdir=workdir,
        project_id=project_id,
        supabase_home=supabase_home,
    )


def prepare_isolated_project(isolated_root: Path) -> tuple[Path, str]:
    """品質用Supabase projectを固有IDとportで複製する。"""
    if isolated_root.exists():
        remove_managed_path(isolated_root)
    workdir = isolated_root
    source = REPOSITORY_ROOT / "supabase"
    target = workdir / "supabase"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".branches", ".temp"),
    )
    project_id = isolated_project_id(isolated_root)
    config_path = target / "config.toml"
    config = config_path.read_text(encoding="utf-8")
    config = re.sub(
        r'^project_id = "[^"]+"$',
        f'project_id = "{project_id}"',
        config,
        count=1,
        flags=re.MULTILINE,
    )
    configured_ports = [int(port) for port in re.findall(r"^port = (\d+)$", config, re.MULTILINE)]
    ports = iter(_available_ports(len(configured_ports), excluded=set(configured_ports)))
    config = re.sub(
        r"^port = \d+$",
        lambda _match: f"port = {next(ports)}",
        config,
        flags=re.MULTILINE,
    )
    config_path.write_text(config, encoding="utf-8")
    return workdir, project_id


def configured_project_id(workdir: Path) -> str:
    """workdirのSupabase設定からlocal project IDを返す。"""
    config = (workdir / "supabase" / "config.toml").read_text(encoding="utf-8")
    match = re.search(r'^project_id = "([^"]+)"$', config, re.MULTILINE)
    if match is None:
        raise EnvironmentBlockedError("Supabase project IDを設定から取得できませんでした。")
    return match.group(1)


def _available_ports(count: int, *, excluded: set[int]) -> list[int]:
    """同時に予約して重複を避けたloopback portを返す。"""
    probes: list[socket.socket] = []
    try:
        while len(probes) < count:
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            if int(probe.getsockname()[1]) in excluded:
                probe.close()
                continue
            probes.append(probe)
        return [int(probe.getsockname()[1]) for probe in probes]
    finally:
        for probe in probes:
            probe.close()


def _supabase_command(arguments: Sequence[str], workdir: Path | None) -> list[str]:
    command = ["supabase", *arguments]
    if workdir is not None:
        command.extend(["--workdir", str(workdir)])
    return command


def _stop_owned_project(
    workdir: Path | None,
    project_id: str | None,
    environment: dict[str, str],
) -> CommandResult | None:
    if workdir is None or project_id is None:
        return None
    managed_isolated = ARTIFACT_ROOT.resolve() in workdir.resolve().parents
    command = ["supabase", "stop", "--project-id", project_id]
    if managed_isolated:
        command.append("--no-backup")
    command.extend(["--workdir", str(workdir)])
    stopped = run_command(
        command,
        timeout_seconds=60,
        environment=environment,
    )
    if stopped.returncode == 0 and workdir.exists() and managed_isolated:
        remove_managed_path(workdir)
    return stopped


def stop_supabase(
    preflight: SupabasePreflight,
    *,
    base_environment: Mapping[str, str] | None = None,
) -> None:
    """このprocessが管理するローカルSupabaseを停止する。"""
    environment = dict(base_environment) if base_environment is not None else quality_environment()
    if preflight.supabase_home is not None:
        environment["SUPABASE_HOME"] = str(preflight.supabase_home)
        environment["SUPABASE_TELEMETRY_DISABLED"] = "true"
    failures: list[str] = []
    if preflight.started_by_process:
        if preflight.workdir is None or preflight.project_id is None:
            failures.append("停止対象のSupabase projectを特定できませんでした。")
        else:
            stopped = _stop_owned_project(preflight.workdir, preflight.project_id, environment)
            if stopped is not None and stopped.returncode != 0:
                failures.append(
                    _failure_message("ローカルSupabaseを停止できませんでした。", stopped)
                )
    if preflight.supabase_home is not None:
        try:
            _remove_supabase_home(preflight.supabase_home)
        except OSError as error:
            failures.append(f"Supabase CLI用の一時profileを削除できませんでした: {error}")
    if failures:
        raise SupabaseOperationError("\n".join(failures))


def _cleanup_preflight_resources(
    workdir: Path,
    project_id: str,
    environment: dict[str, str],
    supabase_home: Path,
    *,
    stop_project: bool,
) -> str:
    failures: list[str] = []
    if stop_project:
        stopped = _stop_owned_project(workdir, project_id, environment)
        if stopped is not None and stopped.returncode != 0:
            failures.append(
                _failure_message("所有するSupabase projectを停止できませんでした。", stopped)
            )
    try:
        _remove_supabase_home(supabase_home)
    except OSError as error:
        failures.append(f"Supabase CLI用の一時profileを削除できませんでした: {error}")
    return "\n".join(failures)


def _with_cleanup_failure(primary: str, cleanup: str) -> str:
    return f"{primary}\ncleanupにも失敗しました:\n{cleanup}" if cleanup else primary


def _remove_supabase_home(profile: Path) -> None:
    if profile.exists() and ARTIFACT_ROOT.resolve() in profile.resolve().parents:
        remove_managed_path(profile)


def _supervisor_state_path() -> Path:
    return ARTIFACT_ROOT / "runtime" / "supabase" / SUPERVISOR_STATE_FILE


def _session_lock_path() -> Path:
    return ARTIFACT_ROOT / "runtime" / "supabase" / SESSION_LOCK_FILE


def _write_supervisor_state(
    run_id: str,
    state: str,
    *,
    session: str | None = None,
    pid: int | None = None,
    report: Path | None = None,
    started_by_process: bool | None = None,
) -> None:
    now = utc_now().isoformat()
    current = _read_supervisor_state()
    started_at = (
        str(current.get("started_at"))
        if current is not None and current.get("run_id") == run_id and current.get("started_at")
        else now
    )
    owns_project = (
        bool(current.get("started_by_process"))
        if started_by_process is None and current is not None and current.get("run_id") == run_id
        else bool(started_by_process)
    )
    write_json(
        _supervisor_state_path(),
        {
            "run_id": run_id,
            "pid": os.getpid() if pid is None else pid,
            "state": state,
            "session": session,
            "started_at": started_at,
            "updated_at": now,
            "report": str(report) if report is not None else None,
            "started_by_process": owns_project,
        },
    )


def _read_supervisor_state() -> dict[str, object] | None:
    try:
        value = json.loads(_supervisor_state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _state_is_active(document: Mapping[str, object]) -> bool:
    state = str(document.get("state", ""))
    try:
        updated = _supervisor_state_path().stat().st_mtime
    except OSError:
        return False
    if state == "reserved":
        return time.time() - updated <= SESSION_RESERVATION_SECONDS
    if state not in {"starting", "ready"}:
        return False
    pid = document.get("pid")
    if not isinstance(pid, int):
        return False
    return _is_live_supervisor(pid)


def _api_port_is_available() -> bool:
    from werewolf_agent.settings import get_settings

    port = get_settings().api_port
    probe = socket.socket()
    probe.settimeout(0.25)
    try:
        return probe.connect_ex(("127.0.0.1", port)) != 0
    finally:
        probe.close()


def reserve_development_session(session: str) -> int:
    """Backend系compoundの開始前に単一の開発セッションを予約する。"""
    try:
        with exclusive_file_lock(_session_lock_path(), timeout_seconds=1):
            current = _read_supervisor_state()
            if current is not None and _state_is_active(current):
                active = current.get("session") or "unknown"
                print(f"開発セッション `{active}` が既に実行中です。", file=sys.stderr)
                return 2
            if session in {"full-stack", "backend", "api"} and not _api_port_is_available():
                print(
                    "API portが既に使用されています。既存のBackendを停止してください。",
                    file=sys.stderr,
                )
                return 2
            run_id = operation_run_id("supabase")
            _write_supervisor_state(run_id, "reserved", session=session)
    except LockTimeoutError:
        print("別の開発セッションが既に実行中です。", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"開発セッションを予約できませんでした: {redact(str(error))}", file=sys.stderr)
        return 1
    print(f"開発セッション `{session}` を予約しました。")
    return 0


def _clear_supervisor_state(run_id: str) -> None:
    path = _supervisor_state_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if document.get("run_id") == run_id:
        path.unlink(missing_ok=True)


def cleanup_development_session() -> int:
    """終了したsupervisorが所有する開発Supabaseだけを停止する。"""
    try:
        with exclusive_file_lock(_session_lock_path(), timeout_seconds=5):
            current = _read_supervisor_state()
            if current is None:
                print("停止対象の開発セッションはありません。")
                return 0
            if _state_is_active(current):
                print("実行中の開発セッションは停止できません。", file=sys.stderr)
                return 2
            run_id = str(current.get("run_id", ""))
            if not run_id:
                print("開発セッション状態が破損しています。", file=sys.stderr)
                return 1
            owner_pid = current.get("pid")
            if not isinstance(owner_pid, int) or owner_pid < 1:
                print("開発セッション状態が破損しています。", file=sys.stderr)
                return 1
            owns_project = bool(current.get("started_by_process"))
            prepared = SupabasePreflight(
                environment={},
                started_by_process=owns_project,
                workdir=REPOSITORY_ROOT if owns_project else None,
                project_id=configured_project_id(REPOSITORY_ROOT) if owns_project else None,
                supabase_home=(
                    ARTIFACT_ROOT / "runtime" / "supabase-home" / f"preflight-{owner_pid}"
                ),
            )
            stop_supabase(prepared)
            _clear_supervisor_state(run_id)
    except LockTimeoutError:
        print("実行中の開発セッションは停止できません。", file=sys.stderr)
        return 2
    except (EnvironmentBlockedError, OSError, SupabaseOperationError) as error:
        print(f"開発セッションを停止できませんでした: {redact(str(error))}", file=sys.stderr)
        return 1
    print("開発セッションの所有resourceを停止しました。")
    return 0


def wait_for_supervisor(*, timeout_seconds: int = 180) -> int:
    """所有processがSupabase準備を完了するまで読み取り専用で待つ。"""
    deadline = time.monotonic() + timeout_seconds
    path = _supervisor_state_path()
    dead_since: dict[str, float] = {}
    while time.monotonic() < deadline:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            state = str(document["state"])
            pid = int(document["pid"])
            run_id = str(document["run_id"])
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            time.sleep(0.25)
            continue
        live = _is_live_supervisor(pid)
        if state == "ready" and live:
            print("ローカルSupabaseの準備完了を確認しました。")
            return 0
        if state in {"blocked", "error"}:
            report = document.get("report")
            print("ローカルSupabaseを準備できませんでした。", file=sys.stderr)
            if report:
                print(f"Supabase operation report: {report}", file=sys.stderr)
            return 2 if state == "blocked" else 1
        if state == "reserved":
            if _state_is_active(document):
                time.sleep(0.25)
                continue
            print("開発セッション予約の有効期限が切れました。", file=sys.stderr)
            return 1
        if state in {"starting", "ready"} and not live:
            first_seen = dead_since.setdefault(run_id, time.monotonic())
            if time.monotonic() - first_seen >= 5:
                print("Supabase supervisorが準備完了前に終了しました。", file=sys.stderr)
                return 1
        if state not in {"starting", "ready"}:
            print("Supabase supervisorの状態が不正です。", file=sys.stderr)
            return 1
        time.sleep(0.25)
    print(
        f"{timeout_seconds}秒以内にローカルSupabaseの準備が完了しませんでした。",
        file=sys.stderr,
    )
    return 2


def _is_live_supervisor(pid: int) -> bool:
    import psutil  # type: ignore[import-untyped]

    try:
        process = psutil.Process(pid)
        command = " ".join(process.cmdline())
        return process.is_running() and "scripts.supabase" in command and "serve" in command
    except (OSError, psutil.Error):
        return False


def serve_supabase(
    *,
    timeout_seconds: int = 180,
    stop_on_exit: bool = False,
    reserved: bool = False,
) -> int:
    """単一lockの所有中だけSupabase supervisorを実行する。"""
    try:
        with exclusive_file_lock(_session_lock_path(), timeout_seconds=1):
            return _serve_supabase_owned(
                timeout_seconds=timeout_seconds,
                stop_on_exit=stop_on_exit,
                reserved=reserved,
            )
    except LockTimeoutError:
        print("別の開発セッションが既に実行中です。", file=sys.stderr)
        return 2


def _serve_supabase_owned(
    *,
    timeout_seconds: int,
    stop_on_exit: bool,
    reserved: bool,
) -> int:
    """VS Code stackの生存期間に合わせてローカルSupabaseを管理する。"""
    session: str | None = None
    current = _read_supervisor_state() if reserved else None
    if reserved:
        if current is None or current.get("state") != "reserved" or not _state_is_active(current):
            print(
                "有効な開発セッション予約がありません。起動をやり直してください。", file=sys.stderr
            )
            return 2
        run_id = str(current.get("run_id", ""))
        session = str(current.get("session", ""))
        if not run_id or not session:
            print("開発セッション予約が破損しています。", file=sys.stderr)
            return 1
    else:
        run_id = operation_run_id("supabase")
    started_at = utc_now().isoformat()
    try:
        _write_supervisor_state(run_id, "starting", session=session)
    except OSError as error:
        print("Supabase supervisorの状態を保存できませんでした。", file=sys.stderr)
        _publish_supabase_report(run_id, "serve", "error", started_at, error)
        return 1
    try:
        prepared = prepare_supabase(
            timeout_seconds=timeout_seconds,
            ownership_callback=lambda owns: _write_supervisor_state(
                run_id,
                "starting",
                session=session,
                started_by_process=owns,
            ),
        )
    except EnvironmentBlockedError as error:
        print(str(error), file=sys.stderr)
        report = _publish_supabase_report(run_id, "serve", "blocked", started_at, error)
        _write_supervisor_state(run_id, "blocked", session=session, report=report)
        return 2
    except SupabaseOperationError as error:
        print(str(error), file=sys.stderr)
        report = _publish_supabase_report(run_id, "serve", "error", started_at, error)
        _write_supervisor_state(run_id, "error", session=session, report=report)
        return 1
    except Exception as error:
        print("Supabase準備中に予期しない実行失敗が発生しました。", file=sys.stderr)
        report = _publish_supabase_report(run_id, "serve", "error", started_at, error)
        _write_supervisor_state(run_id, "error", session=session, report=report)
        return 1
    try:
        _write_supervisor_state(
            run_id,
            "ready",
            session=session,
            started_by_process=prepared.started_by_process,
        )
    except OSError as error:
        cleanup_error: BaseException | None = None
        if stop_on_exit:
            try:
                stop_supabase(prepared)
            except (EnvironmentBlockedError, SupabaseOperationError) as caught:
                cleanup_error = caught
        print("Supabase supervisorの準備完了状態を保存できませんでした。", file=sys.stderr)
        combined = (
            SupabaseOperationError(f"{error}\ncleanupにも失敗しました: {cleanup_error}")
            if cleanup_error is not None
            else error
        )
        report = _publish_supabase_report(run_id, "serve", "error", started_at, combined)
        with suppress(OSError):
            _write_supervisor_state(run_id, "error", session=session, report=report)
        return 1
    print("ローカルSupabaseの準備が完了しました。停止するにはCtrl+Cを押してください。", flush=True)
    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    previous_handlers: list[tuple[signal.Signals, Any]] = []
    handled_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        handled_signals.append(signal.SIGBREAK)
    try:
        for handled_signal in handled_signals:
            previous_handlers.append((handled_signal, signal.getsignal(handled_signal)))
            signal.signal(handled_signal, request_stop)
        with suppress(KeyboardInterrupt):
            stop_event.wait()
    finally:
        for handled_signal, previous_handler in previous_handlers:
            signal.signal(handled_signal, previous_handler)
    try:
        if stop_on_exit:
            stop_supabase(prepared)
    except (EnvironmentBlockedError, SupabaseOperationError) as error:
        print(str(error), file=sys.stderr)
        report = _publish_supabase_report(run_id, "serve", "error", started_at, error)
        _write_supervisor_state(run_id, "error", session=session, report=report)
        return 1
    _publish_supabase_report(run_id, "serve", "passed", started_at)
    _clear_supervisor_state(run_id)
    return 0


def _failure_message(message: str, result: CommandResult) -> str:
    detail = redact("\n".join(result.output.strip().splitlines()[-20:]))
    return f"{message}\n{detail}" if detail else message


def build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数を構築する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=_positive_int, default=180)
    return parser


def _positive_int(value: str) -> int:
    """1以上の整数をargparse向けに検証する。"""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください。")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """Supabase事前確認を実行する。"""
    arguments = build_parser().parse_args(argv)
    run_id = operation_run_id("supabase")
    started_at = utc_now().isoformat()
    try:
        prepared = prepare_supabase(timeout_seconds=arguments.timeout)
    except EnvironmentBlockedError as error:
        print(str(error), file=sys.stderr)
        _publish_supabase_report(run_id, "preflight", "blocked", started_at, error)
        return 2
    except SupabaseOperationError as error:
        print(str(error), file=sys.stderr)
        _publish_supabase_report(run_id, "preflight", "error", started_at, error)
        return 1
    except Exception as error:
        print("Supabase準備中に予期しない実行失敗が発生しました。", file=sys.stderr)
        _publish_supabase_report(run_id, "preflight", "error", started_at, error)
        return 1
    try:
        stop_supabase(prepared)
    except (EnvironmentBlockedError, SupabaseOperationError) as error:
        print(str(error), file=sys.stderr)
        _publish_supabase_report(run_id, "preflight", "error", started_at, error)
        return 1
    print("ローカルSupabaseの準備が完了しました。")
    _publish_supabase_report(run_id, "preflight", "passed", started_at)
    return 0


def _publish_supabase_report(
    run_id: str,
    command: str,
    state: str,
    started_at: str,
    error: BaseException | None = None,
) -> Path | None:
    """Supabase operationの共通成果物をbest effortで公開する。"""
    detail = str(error) if error is not None else ""
    safe_detail = redact(detail)
    report = {
        "run_id": run_id,
        "command": command,
        "state": state,
        "started_at": started_at,
        "finished_at": utc_now().isoformat(),
        "observations": ["Supabase準備が完了しました。"] if state == "passed" else [],
        "confirmed_causes": [safe_detail] if safe_detail else [],
        "unconfirmed_scope": [] if state == "passed" else ["失敗段階より後は未確認です。"],
        "next_actions": [] if state == "passed" else ["原因を解消して再実行してください。"],
        "related_artifacts": [f"operations/supabase/{run_id}/report.json"],
    }
    summary = f"# Supabase {command}\n\n- 判定: `{state}`\n" + (
        f"- 原因: {safe_detail}\n" if safe_detail else ""
    )
    try:
        path = publish_operation(
            "supabase",
            run_id,
            report,
            summary,
            failure_logs={command: safe_detail} if safe_detail else None,
        )
    except Exception as publish_error:
        print(f"Supabase operation reportを保存できませんでした: {publish_error}", file=sys.stderr)
        return None
    print(f"Supabase operation report: {path}", file=sys.stderr)
    return path


if __name__ == "__main__":
    raise SystemExit(main())
