"""Lock fileに従って開発環境を検査し、明示的に準備する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts._infra.artifacts import LAYOUT
from scripts._infra.locking import LockTimeoutError, exclusive_file_lock
from scripts._infra.operations import operation_run_id, publish_operation
from scripts._infra.process import (
    ARTIFACT_ROOT,
    REPOSITORY_ROOT,
    CommandResult,
    redact,
    remove_managed_path,
    utc_now,
)
from scripts.supabase.constants import LOCAL_EXCLUDED_SERVICES_CSV, SUPPORTED_CLI_VERSION

STATE_ROOT = ARTIFACT_ROOT / "runtime" / "environment"
LOCK_PATH = STATE_ROOT / "setup.lock"
PROFILES = ("focus", "check", "release", "deep")
INPUT_PROFILES = ("auto", *PROFILES)
PYTHON_INPUTS = ("pyproject.toml", "uv.lock")
RELEASE_INPUTS = (
    "compose.yaml",
    "docker",
    "contracts",
    "scripts/environment",
    "scripts/supabase",
    "src",
    ".streamlit",
    "supabase",
)
RUNTIME_IMAGE = "werewolf-agent-quality-app:latest"
E2E_IMAGE = "werewolf-agent-quality-e2e:latest"
QUALITY_BUILDER = "werewolf-agent-quality"
IMAGE_FINGERPRINT_LABEL_PREFIX = "io.github.satter0827.werewolf-agent.quality"
SUPABASE_CLI_VERSION = SUPPORTED_CLI_VERSION

ERROR_UV_UNAVAILABLE = "environment.uv_unavailable"
ERROR_PYTHON_UNSUPPORTED = "environment.python_unsupported"
ERROR_DOCKER_CLI_UNAVAILABLE = "environment.docker_cli_unavailable"
ERROR_DOCKER_DAEMON_UNAVAILABLE = "environment.docker_daemon_unavailable"
ERROR_BUILDX_UNAVAILABLE = "environment.buildx_unavailable"
ERROR_SUPABASE_CLI_UNAVAILABLE = "environment.supabase_cli_unavailable"
ERROR_SUPABASE_VERSION_MISMATCH = "environment.supabase_cli_version_mismatch"
ERROR_COMMAND_FAILED = "environment.command_failed"
ERROR_CLEANUP_FAILED = "environment.cleanup_failed"
ERROR_FINGERPRINT_MISMATCH = "environment.fingerprint_mismatch"


def prepare_isolated_project(isolated_root: Path) -> tuple[Path, str]:
    """Deep環境が必要になった時点でSupabase用依存を読み込む。"""
    from scripts.supabase.preflight import prepare_isolated_project as prepare

    return prepare(isolated_root)


@dataclass(frozen=True, slots=True)
class EnvironmentCheck:
    """環境を変更せずに得た一つの判定。"""

    id: str
    state: str
    summary: str
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class EnvironmentReport:
    """人と機械が同じ根拠を参照する環境診断結果。"""

    schema_version: int
    run_id: str
    command: str
    requested_profile: str
    resolved_profile: str
    state: str
    started_at: str
    finished_at: str
    checks: list[EnvironmentCheck]
    observations: list[str]
    confirmed_causes: list[str]
    unconfirmed_scope: list[str]
    next_actions: list[str]
    related_artifacts: list[str]
    error_code: str | None = None


@dataclass(slots=True)
class _ExecutionFailure:
    stage: str
    result: CommandResult
    error_code: str = ERROR_COMMAND_FAILED


def dependency_fingerprint(profile: str) -> str:
    """Lockとrelease入力から依存環境fingerprintを返す。"""
    digest = hashlib.sha256()
    inputs = [REPOSITORY_ROOT / relative for relative in PYTHON_INPUTS]
    if profile in {"release", "deep"}:
        for relative in RELEASE_INPUTS:
            path = REPOSITORY_ROOT / relative
            inputs.extend(
                candidate
                for candidate in ([path] if path.is_file() else path.rglob("*"))
                if candidate.is_file() and not {"__pycache__", "dist"}.intersection(candidate.parts)
            )
    for path in sorted(set(inputs)):
        digest.update(path.relative_to(REPOSITORY_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    digest.update(profile.encode())
    return digest.hexdigest()


def python_installation_fingerprint() -> str:
    """Installed distributionの名前・version・RECORDを固定順でhash化する。"""
    digest = hashlib.sha256()
    records: list[tuple[str, str, str]] = []
    for distribution in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"].casefold())
        record_text = distribution.read_text("RECORD")
        record_hash = hashlib.sha256((record_text or "MISSING").encode()).hexdigest()
        records.append((name, distribution.version, record_hash))
    for entry in sorted(records):
        digest.update("\0".join(entry).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def inspect_environment(
    profile: str = "check", *, command: str = "check", run_id: str | None = None
) -> EnvironmentReport:
    """resourceを変更せず、指定profileの準備状態を返す。"""
    started = utc_now()
    requested = profile
    resolved = _resolve_profile(profile)
    actual_run_id = run_id or operation_run_id("environment")
    checks = _prerequisite_checks(resolved, actual_run_id)
    if all(item.state == "passed" for item in checks):
        try:
            checks.append(_state_check(resolved))
        except Exception as error:
            checks.append(
                EnvironmentCheck(
                    ERROR_COMMAND_FAILED,
                    "error",
                    "環境状態の検査中に予期しない実行失敗が発生しました。",
                    {"error_type": type(error).__name__, "detail": redact(str(error))},
                )
            )
    failures = [item for item in checks if item.state != "passed"]
    selected = next((item for item in failures if item.state == "error"), None)
    selected = selected or (failures[0] if failures else None)
    state = (
        "error"
        if any(item.state == "error" for item in failures)
        else ("blocked" if failures else "passed")
    )
    return EnvironmentReport(
        schema_version=1,
        run_id=actual_run_id,
        command=command,
        requested_profile=requested,
        resolved_profile=resolved,
        state=state,
        started_at=started.isoformat(),
        finished_at=utc_now().isoformat(),
        checks=checks,
        observations=[item.summary for item in checks],
        confirmed_causes=[item.summary for item in failures],
        unconfirmed_scope=[] if state == "passed" else ["失敗した検査より後の項目は未確認です。"],
        next_actions=_next_actions(selected.id if selected is not None else None, resolved),
        related_artifacts=[_operation_report_path(actual_run_id)],
        error_code=selected.id if selected is not None else None,
    )


def check(profile: str = "check") -> EnvironmentReport:
    """指定profileを検査し、operation成果物を公開する。"""
    report = inspect_environment(profile)
    _publish_report(report)
    return report


def setup(profile: str = "check") -> EnvironmentReport:
    """指定profileを事前検査後に準備し、operation成果物を公開する。"""
    requested = profile
    resolved = _resolve_profile(profile)
    run_id = operation_run_id("environment")
    started = utc_now()
    prerequisite_checks = _prerequisite_checks(resolved, run_id)
    prerequisite_failures = [item for item in prerequisite_checks if item.state != "passed"]
    if prerequisite_failures:
        selected = next(
            (item for item in prerequisite_failures if item.state == "error"),
            prerequisite_failures[0],
        )
        state = "error" if selected.state == "error" else "blocked"
        report = EnvironmentReport(
            1,
            run_id,
            "setup",
            requested,
            resolved,
            state,
            started.isoformat(),
            utc_now().isoformat(),
            prerequisite_checks,
            [item.summary for item in prerequisite_checks],
            [item.summary for item in prerequisite_failures],
            ["変更処理は開始していません。"],
            _next_actions(selected.id, resolved),
            [_operation_report_path(run_id)],
            selected.id,
        )
        _publish_report(report)
        return report

    failure: _ExecutionFailure | None = None
    cleanup_failure: _ExecutionFailure | None = None
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        with exclusive_file_lock(LOCK_PATH, timeout_seconds=600):
            failure, cleanup_failure = _setup_locked(resolved, run_id)
    except LockTimeoutError:
        failure = _synthetic_failure("lock", "依存環境の準備lockを取得できませんでした。")
    except OSError as error:
        failure = _synthetic_failure("setup", str(error))

    checks = list(prerequisite_checks)
    failure_logs: dict[str, str] = {}
    for item in (failure, cleanup_failure):
        if item is None:
            continue
        summary = (
            "隔離Supabaseのcleanupに失敗しました。"
            if item.error_code == ERROR_CLEANUP_FAILED
            else f"{item.stage}に失敗しました。"
        )
        checks.append(
            EnvironmentCheck(
                item.error_code,
                "error",
                summary,
                {
                    "stage": item.stage,
                    "exit_code": item.result.returncode,
                    "duration_seconds": round(item.result.duration_seconds, 3),
                    "log": f"logs/{item.stage}.log",
                },
            )
        )
        failure_logs[item.stage] = item.result.output
    state = "passed" if failure is None and cleanup_failure is None else "error"
    report = EnvironmentReport(
        1,
        run_id,
        "setup",
        requested,
        resolved,
        state,
        started.isoformat(),
        utc_now().isoformat(),
        checks,
        [item.summary for item in checks],
        [item.summary for item in checks if item.state != "passed"],
        [] if state == "passed" else ["失敗したstageより後の準備状態は未確認です。"],
        []
        if state == "passed"
        else [f"原因を解消してenvironment setup {resolved}を再実行してください。"],
        [_operation_report_path(run_id)],
        None if state == "passed" else checks[-1].id,
    )
    _publish_report(report, failure_logs=failure_logs)
    return report


def _setup_locked(
    profile: str, run_id: str
) -> tuple[_ExecutionFailure | None, _ExecutionFailure | None]:
    uv = shutil.which("uv") or "uv"
    synced = _execute((uv, "sync", "--frozen", "--all-groups", "--all-extras"), timeout=600)
    if synced.returncode != 0:
        return _ExecutionFailure("python-sync", synced), None
    supabase_images: list[dict[str, str]] = []
    cleanup_failure: _ExecutionFailure | None = None
    if profile in {"release", "deep"}:
        docker = shutil.which("docker") or "docker"
        if not _command_succeeds((docker, "buildx", "inspect", QUALITY_BUILDER)):
            created = _execute(
                (
                    docker,
                    "buildx",
                    "create",
                    "--name",
                    QUALITY_BUILDER,
                    "--driver",
                    "docker-container",
                )
            )
            if created.returncode != 0:
                return _ExecutionFailure("buildx-create", created), None
        build_environment = {**os.environ, "BUILDX_BUILDER": QUALITY_BUILDER}
        for image, key, fingerprint, command in _image_builds(docker):
            if _image_fingerprint_matches(image, key, fingerprint):
                continue
            built = _execute(command, environment=build_environment, timeout=1200)
            if built.returncode != 0:
                return _ExecutionFailure(f"{key}-image", built), None
        supabase_failure, cleanup_failure, supabase_images = _prepare_supabase_images(run_id)
        if supabase_failure is not None:
            return supabase_failure, cleanup_failure
        if cleanup_failure is not None:
            return None, cleanup_failure
        pruned = _execute(
            (
                docker,
                "buildx",
                "prune",
                "--builder",
                QUALITY_BUILDER,
                "--max-used-space",
                f"{_docker_cache_max_gib()}GB",
                "--force",
            ),
            timeout=300,
        )
        if pruned.returncode != 0:
            return _ExecutionFailure("buildx-prune", pruned), cleanup_failure
    _write_state(profile, supabase_images)
    return None, cleanup_failure


def _prepare_supabase_images(
    run_id: str,
) -> tuple[_ExecutionFailure | None, _ExecutionFailure | None, list[dict[str, str]]]:
    workdir, project_id = prepare_isolated_project(
        LAYOUT.runtime / "supabase" / f"environment-{run_id}"
    )
    profile = LAYOUT.runtime / "supabase-home" / run_id
    environment = {
        **os.environ,
        "SUPABASE_HOME": str(profile),
        "SUPABASE_TELEMETRY_DISABLED": "true",
    }
    start = _execute(
        ("supabase", "start", "--exclude", LOCAL_EXCLUDED_SERVICES_CSV, "--workdir", str(workdir)),
        environment=environment,
        timeout=600,
    )
    images = _supabase_project_images(project_id, environment) if start.returncode == 0 else []
    stopped = _execute(
        ("supabase", "stop", "--project-id", project_id, "--no-backup", "--workdir", str(workdir)),
        environment=environment,
        timeout=120,
    )
    cleanup_results: list[CommandResult] = []
    if stopped.returncode != 0:
        cleanup_results.append(stopped)
    elif workdir.exists():
        cleanup_result = _remove_operation_path(workdir)
        if cleanup_result is not None:
            cleanup_results.append(cleanup_result)
    if profile.exists():
        cleanup_result = _remove_operation_path(profile)
        if cleanup_result is not None:
            cleanup_results.append(cleanup_result)
    if start.returncode != 0:
        failure = _ExecutionFailure("supabase-start", start)
    elif not images:
        failure = _synthetic_failure(
            "supabase-images",
            "起動したSupabase projectのimage IDを取得できませんでした。",
        )
    else:
        failure = None
    cleanup = _combined_cleanup_failure(cleanup_results)
    return failure, cleanup, images


def _remove_operation_path(path: Path) -> CommandResult | None:
    import time

    started = time.monotonic()
    try:
        remove_managed_path(path)
    except OSError as error:
        return CommandResult(
            ["remove", str(path)],
            1,
            time.monotonic() - started,
            str(error),
        )
    return None


def _combined_cleanup_failure(results: list[CommandResult]) -> _ExecutionFailure | None:
    if not results:
        return None
    combined = CommandResult(
        ["cleanup"],
        next(result.returncode for result in results if result.returncode != 0),
        sum(result.duration_seconds for result in results),
        "\n".join(result.output for result in results if result.output),
        any(result.timed_out for result in results),
    )
    return _ExecutionFailure("cleanup", combined, ERROR_CLEANUP_FAILED)


def _supabase_project_images(project_id: str, environment: dict[str, str]) -> list[dict[str, str]]:
    listed = _execute(
        (
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label=com.supabase.cli.project={project_id}",
            "--format",
            "{{.Image}}",
        ),
        environment=environment,
    )
    images: list[dict[str, str]] = []
    for reference in sorted({line.strip() for line in listed.output.splitlines() if line.strip()}):
        image_id = _image_id(reference)
        if image_id is not None:
            images.append({"reference": reference, "image_id": image_id})
    return images


def _prerequisite_checks(profile: str, run_id: str) -> list[EnvironmentCheck]:
    uv = shutil.which("uv")
    if uv is None:
        return [EnvironmentCheck(ERROR_UV_UNAVAILABLE, "blocked", "uvを確認できません。")]
    checks = [EnvironmentCheck("environment.uv", "passed", f"uvを確認しました: {uv}")]
    if not (3, 11) <= sys.version_info[:2] <= (3, 14):
        return [
            *checks,
            EnvironmentCheck(
                ERROR_PYTHON_UNSUPPORTED,
                "blocked",
                "Python 3.11から3.14が必要です。",
                {"actual": ".".join(str(item) for item in sys.version_info[:3])},
            ),
        ]
    checks.append(
        EnvironmentCheck(
            "environment.python", "passed", f"Python {sys.version.split()[0]}を確認しました。"
        )
    )
    if profile not in {"release", "deep"}:
        return checks
    docker = shutil.which("docker")
    if docker is None:
        return [
            *checks,
            EnvironmentCheck(
                ERROR_DOCKER_CLI_UNAVAILABLE, "blocked", "Docker CLIを確認できません。"
            ),
        ]
    checks.append(
        EnvironmentCheck("environment.docker_cli", "passed", f"Docker CLIを確認しました: {docker}")
    )
    info = _execute((docker, "info"), timeout=30)
    if info.returncode != 0:
        return [
            *checks,
            EnvironmentCheck(
                ERROR_DOCKER_DAEMON_UNAVAILABLE,
                "blocked",
                "Docker daemonへ接続できません。",
                {"detail": _tail(info.output, lines=2)},
            ),
        ]
    checks.append(
        EnvironmentCheck("environment.docker_daemon", "passed", "Docker daemonへ接続できました。")
    )
    buildx = _execute((docker, "buildx", "version"), timeout=30)
    if buildx.returncode != 0:
        return [
            *checks,
            EnvironmentCheck(
                ERROR_BUILDX_UNAVAILABLE, "blocked", "Docker Buildxを確認できません。"
            ),
        ]
    checks.append(EnvironmentCheck("environment.buildx", "passed", "Docker Buildxを確認しました。"))
    supabase = shutil.which("supabase")
    if supabase is None:
        return [
            *checks,
            EnvironmentCheck(
                ERROR_SUPABASE_CLI_UNAVAILABLE, "blocked", "Supabase CLIを確認できません。"
            ),
        ]
    profile_root = LAYOUT.runtime / "supabase-home" / f"inspect-{run_id}"
    version = _execute(
        (supabase, "--version"),
        environment={
            **os.environ,
            "SUPABASE_HOME": str(profile_root),
            "SUPABASE_TELEMETRY_DISABLED": "true",
        },
        timeout=30,
    )
    actual = version.output.strip()
    if version.returncode != 0:
        checks.append(
            EnvironmentCheck(
                ERROR_SUPABASE_CLI_UNAVAILABLE,
                "blocked",
                "Supabase CLIを実行できません。",
                {"detail": _tail(version.output)},
            )
        )
    elif actual != SUPABASE_CLI_VERSION:
        checks.append(
            EnvironmentCheck(
                ERROR_SUPABASE_VERSION_MISMATCH,
                "blocked",
                f"Supabase CLIは{SUPABASE_CLI_VERSION}が必要です。",
                {"actual": actual, "expected": SUPABASE_CLI_VERSION},
            )
        )
    else:
        checks.append(
            EnvironmentCheck(
                "environment.supabase_cli", "passed", f"Supabase CLI {actual}を確認しました。"
            )
        )
    cleanup = _remove_operation_path(profile_root) if profile_root.exists() else None
    if cleanup is not None:
        checks.append(
            EnvironmentCheck(
                ERROR_CLEANUP_FAILED,
                "error",
                "Supabase CLI用の一時profileを削除できませんでした。",
                {
                    "stage": "supabase-profile-cleanup",
                    "exit_code": cleanup.returncode,
                    "duration_seconds": round(cleanup.duration_seconds, 3),
                    "detail": _tail(cleanup.output),
                },
            )
        )
    return checks


def _state_check(profile: str) -> EnvironmentCheck:
    if not (REPOSITORY_ROOT / ".venv").is_dir():
        return EnvironmentCheck(
            ERROR_FINGERPRINT_MISMATCH, "blocked", "Python環境が準備されていません。"
        )
    state = _read_state(profile)
    if state is None or state.get("fingerprint") != dependency_fingerprint(profile):
        return EnvironmentCheck(
            ERROR_FINGERPRINT_MISMATCH, "blocked", f"{profile}環境が現在の入力に対応していません。"
        )
    if profile in {"release", "deep"}:
        recorded_context = state.get("docker_context")
        current_context = _docker_context()
        if recorded_context != current_context:
            return EnvironmentCheck(
                ERROR_FINGERPRINT_MISMATCH,
                "blocked",
                "Docker contextが準備時から変わっています。",
                {"recorded": recorded_context, "current": current_context},
            )
        if state.get("supabase_cli_version") != SUPABASE_CLI_VERSION:
            return EnvironmentCheck(
                ERROR_FINGERPRINT_MISMATCH,
                "blocked",
                "Supabase CLIの準備記録が現在の固定versionと一致しません。",
                {
                    "recorded": state.get("supabase_cli_version"),
                    "current": SUPABASE_CLI_VERSION,
                },
            )
        if not _image_fingerprint_matches(
            RUNTIME_IMAGE, "application", _application_image_fingerprint()
        ):
            return EnvironmentCheck(
                ERROR_FINGERPRINT_MISMATCH,
                "blocked",
                "application imageが現在のsourceに対応していません。",
            )
        if not _image_fingerprint_matches(
            E2E_IMAGE, "browser-dependencies", _e2e_image_fingerprint()
        ):
            return EnvironmentCheck(
                ERROR_FINGERPRINT_MISMATCH, "blocked", "E2E imageが現在の依存に対応していません。"
            )
        images = state.get("supabase_images")
        if not isinstance(images, list) or not images:
            return EnvironmentCheck(
                ERROR_FINGERPRINT_MISMATCH, "blocked", "Supabase imageの準備記録がありません。"
            )
        for image in images:
            if not isinstance(image, dict) or _image_id(
                str(image.get("reference", ""))
            ) != image.get("image_id"):
                return EnvironmentCheck(
                    ERROR_FINGERPRINT_MISMATCH,
                    "blocked",
                    "Supabase imageの構成が準備時から変わっています。",
                )
    return EnvironmentCheck("environment.ready", "passed", f"{profile}環境は準備済みです。")


def _read_state(profile: str) -> dict[str, object] | None:
    try:
        value = json.loads(_state_path(profile).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_state(profile: str, supabase_images: list[dict[str, str]]) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    target = _state_path(profile)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "fingerprint": dependency_fingerprint(profile),
                "profile": profile,
                "docker_context": _docker_context() if profile in {"release", "deep"} else None,
                "supabase_cli_version": SUPABASE_CLI_VERSION
                if profile in {"release", "deep"}
                else None,
                "supabase_images": supabase_images,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def _state_path(profile: str) -> Path:
    return STATE_ROOT / f"{profile}.json"


def _image_builds(docker: str) -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    application_fingerprint = _application_image_fingerprint()
    browser_fingerprint = _e2e_image_fingerprint()
    return (
        (
            RUNTIME_IMAGE,
            "application",
            application_fingerprint,
            (
                docker,
                "buildx",
                "build",
                "--builder",
                QUALITY_BUILDER,
                "--load",
                "--label",
                f"{_image_fingerprint_label('application')}={application_fingerprint}",
                "--target",
                "runtime",
                "--file",
                "docker/backend.Dockerfile",
                "--tag",
                RUNTIME_IMAGE,
                ".",
            ),
        ),
        (
            E2E_IMAGE,
            "browser-dependencies",
            browser_fingerprint,
            (
                docker,
                "buildx",
                "build",
                "--builder",
                QUALITY_BUILDER,
                "--load",
                "--label",
                f"{_image_fingerprint_label('browser-dependencies')}={browser_fingerprint}",
                "--file",
                "docker/e2e.Dockerfile",
                "--tag",
                E2E_IMAGE,
                ".",
            ),
        ),
    )


def _image_fingerprint_matches(image: str, key: str, fingerprint: str) -> bool:
    return _image_label(image, _image_fingerprint_label(key)) == fingerprint


def _image_fingerprint_label(key: str) -> str:
    return f"{IMAGE_FINGERPRINT_LABEL_PREFIX}.{key}"


def _image_label(image: str, label: str) -> str | None:
    result = _execute(
        (
            "docker",
            "image",
            "inspect",
            "--format",
            f'{{{{ index .Config.Labels "{label}" }}}}',
            image,
        ),
        timeout=30,
    )
    value = result.output.strip()
    return value if result.returncode == 0 and value and value != "<no value>" else None


def _image_id(image: str) -> str | None:
    if not image:
        return None
    result = _execute(("docker", "image", "inspect", "--format", "{{.Id}}", image), timeout=30)
    value = result.output.strip()
    return value if result.returncode == 0 and value else None


def _application_image_fingerprint() -> str:
    return _paths_fingerprint(
        (
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "docker/backend.Dockerfile",
            "src",
            "scripts/_infra",
            "scripts/supabase",
            "scripts/__init__.py",
            "supabase",
            ".streamlit",
        )
    )


def _e2e_image_fingerprint() -> str:
    return _paths_fingerprint(("pyproject.toml", "uv.lock", "README.md", "docker/e2e.Dockerfile"))


def _paths_fingerprint(relatives: Sequence[str]) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for relative in relatives:
        path = REPOSITORY_ROOT / relative
        files.extend(
            item for item in ([path] if path.is_file() else path.rglob("*")) if item.is_file()
        )
    for path in sorted(set(files)):
        digest.update(path.relative_to(REPOSITORY_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _docker_cache_max_gib() -> int:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        return int(tomllib.load(stream)["tool"]["werewolf-quality"]["docker_builder_cache_max_gib"])


def _docker_context() -> str:
    result = _execute(("docker", "context", "show"), timeout=30)
    return result.output.strip() if result.returncode == 0 else "unavailable"


def _execute(
    command: Sequence[str], *, environment: dict[str, str] | None = None, timeout: int = 60
) -> CommandResult:
    import time

    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
        return CommandResult(
            list(command),
            completed.returncode,
            time.monotonic() - started,
            (completed.stdout or "") + (completed.stderr or ""),
        )
    except FileNotFoundError as error:
        return CommandResult(list(command), 127, time.monotonic() - started, str(error))
    except subprocess.TimeoutExpired as error:
        stdout = _decode_subprocess_output(error.stdout)
        stderr = _decode_subprocess_output(error.stderr)
        return CommandResult(
            list(command),
            124,
            time.monotonic() - started,
            stdout + stderr,
            True,
        )


def _decode_subprocess_output(output: str | bytes | None) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def _command_succeeds(command: Sequence[str]) -> bool:
    return _execute(command, timeout=30).returncode == 0


def _synthetic_failure(stage: str, message: str) -> _ExecutionFailure:
    return _ExecutionFailure(stage, CommandResult([stage], 1, 0.0, message))


def _resolve_profile(profile: str) -> str:
    if profile not in INPUT_PROFILES:
        raise ValueError(f"未定義の環境profileです: {profile}")
    if profile != "auto":
        return profile
    from scripts.quality.impact import decide

    return decide().profile


def _next_actions(error_code: str | None, profile: str) -> list[str]:
    if error_code is None:
        return []
    if error_code == ERROR_DOCKER_DAEMON_UNAVAILABLE:
        return [
            "Docker Desktopを起動してください。",
            f"environment setup {profile}を再実行してください。",
        ]
    if error_code == ERROR_FINGERPRINT_MISMATCH:
        return [f"environment setup {profile}を実行してください。"]
    if error_code == ERROR_SUPABASE_VERSION_MISMATCH:
        return [f"Supabase CLI {SUPABASE_CLI_VERSION}をインストールしてください。"]
    return [f"{error_code}を解消してenvironment setup {profile}を再実行してください。"]


def _tail(value: str, *, lines: int = 20) -> str:
    return redact("\n".join(value.strip().splitlines()[-lines:]))


def _operation_report_path(run_id: str) -> str:
    return f"operations/environment/{run_id}/report.json"


def _summary(report: EnvironmentReport) -> str:
    lines = [
        f"# 環境{('準備' if report.command == 'setup' else '検査')}: {report.resolved_profile}",
        "",
        f"- 判定: `{report.state}`",
        f"- Run ID: `{report.run_id}`",
        "",
        "## 状況",
        "",
        *(f"- `{item.id}`: {item.summary}" for item in report.checks),
    ]
    for item in report.checks:
        detail = item.evidence.get("detail")
        if item.state != "passed" and isinstance(detail, str) and detail:
            lines.extend([f"  - 詳細: {detail.replace(chr(10), chr(10) + '    ')}"])
    if report.confirmed_causes:
        lines.extend(
            ["", "## 確認できた原因", "", *(f"- {item}" for item in report.confirmed_causes)]
        )
    if report.unconfirmed_scope:
        lines.extend(["", "## 未確認範囲", "", *(f"- {item}" for item in report.unconfirmed_scope)])
    if report.next_actions:
        lines.extend(["", "## 次の操作", "", *(f"- {item}" for item in report.next_actions)])
    return "\n".join(lines)


def _publish_report(
    report: EnvironmentReport, *, failure_logs: dict[str, str] | None = None
) -> Path | None:
    try:
        return publish_operation(
            "environment",
            report.run_id,
            asdict(report),
            _summary(report),
            failure_logs=failure_logs,
        )
    except Exception as error:
        report.related_artifacts.clear()
        print(
            f"警告: 診断reportを保存できませんでした: {redact(str(error))}",
            file=sys.stderr,
        )
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "setup"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("profile", choices=INPUT_PROFILES, nargs="?", default="check")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        report = (
            setup(arguments.profile) if arguments.command == "setup" else check(arguments.profile)
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"環境操作を記録できませんでした: {redact(str(error))}")
        return 1
    print(_summary(report))
    if report.related_artifacts:
        print(f"\n診断report: {REPOSITORY_ROOT / '.werewolf-agent' / report.related_artifacts[0]}")
    if report.state == "passed":
        return 0
    return 2 if report.state == "blocked" else 1


__all__ = [
    "E2E_IMAGE",
    "PROFILES",
    "RUNTIME_IMAGE",
    "SUPABASE_CLI_VERSION",
    "EnvironmentCheck",
    "EnvironmentReport",
    "check",
    "dependency_fingerprint",
    "inspect_environment",
    "main",
    "python_installation_fingerprint",
    "setup",
]
