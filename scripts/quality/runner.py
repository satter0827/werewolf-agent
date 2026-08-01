"""ローカルとCIで共有する品質ゲート実行基盤。"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import os
import shutil
import sys
import tempfile
import time
import tomllib
from collections.abc import Sequence
from pathlib import Path

import psutil  # type: ignore[import-untyped]

from scripts._infra.locking import LockTimeoutError, exclusive_file_lock
from scripts._infra.process import (
    ARTIFACT_ROOT,
    QUALITY_COMPOSE_PROJECT_NAME,
    REPOSITORY_ROOT,
    TEMPORARY_CACHE_DIRECTORIES,
    TEMPORARY_ROOT,
    CommandResult,
    EnvironmentBlockedError,
    create_run_directory,
    quality_environment,
    redact,
    redact_artifacts,
    remove_managed_path,
    remove_temporary_path,
    run_command,
    utc_now,
)
from scripts.environment.manager import python_installation_fingerprint
from scripts.quality.gates import services as services_gate
from scripts.quality.models import (
    FailureState,
    Gate,
    GateResult,
    QualitySettings,
    RunContext,
    State,
)
from scripts.quality.reporting import (
    append_events as _append_events,
)
from scripts.quality.reporting import (
    write_summary as _write_summary,
)
from scripts.quality.repository import ChangeSet, capture_snapshot, resolve_changes

PROFILE_ORDER = ("focus", "check", "release", "deep")
BUILD_DIRECTORIES = (
    ARTIFACT_ROOT / "outputs",
    ARTIFACT_ROOT / "cache",
    ARTIFACT_ROOT / "quality",
)
QUALITY_RESOURCE_CONFIRMATION = "DELETE"


def load_quality_settings() -> QualitySettings:
    """品質設定をpyproject.tomlから検証して読み込む。"""
    document = _load_pyproject()
    tool = _required_table(document, "tool", "tool")
    quality = _required_table(tool, "werewolf-quality", "tool.werewolf-quality")
    timeouts = _required_table(quality, "timeouts", "tool.werewolf-quality.timeouts")
    max_jobs = _required_int(quality, "max_jobs", minimum=1)
    return QualitySettings(
        default_jobs=_required_int(quality, "default_jobs", minimum=1, maximum=max_jobs),
        max_jobs=max_jobs,
        benchmark_min_rounds=_required_int(quality, "benchmark_min_rounds", minimum=1),
        timeouts={
            profile: _required_int(timeouts, profile, minimum=1) for profile in PROFILE_ORDER
        },
    )


def _load_pyproject() -> dict[str, object]:
    """pyproject.tomlを品質検査向けに読み込む。"""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def _required_table(
    parent: dict[str, object],
    key: str,
    path: str,
) -> dict[str, object]:
    """必須TOML tableを返す。"""
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{path}をTOML tableとして定義してください。")
    return value


def _required_int(
    parent: dict[str, object],
    key: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    """下限付きの必須整数設定を返す。"""
    value = parent.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        range_text = f"{minimum}以上{maximum}以下" if maximum is not None else f"{minimum}以上"
        raise ValueError(f"{key}には{range_text}の整数を指定してください。")
    return value


def _profile_stages(
    profile: str,
    jobs: int,
    run_dir: Path | None = None,
    settings: QualitySettings | None = None,
    fresh: bool = False,
) -> list[list[Gate]]:
    """担当moduleのgateを依存関係と排他resourceから構成する。"""
    from scripts.quality.profiles import build_profile

    resolved_settings = settings or load_quality_settings()
    resolved_run_dir = run_dir or TEMPORARY_ROOT / "quality" / "runs" / "unbound"
    return build_profile(
        profile,
        run_dir=resolved_run_dir,
        settings=resolved_settings,
        jobs=jobs,
        fresh=fresh,
    )


def clean() -> list[Path]:
    """再生成可能なbuildとcacheだけを削除する。"""
    removed: list[Path] = []
    for path in BUILD_DIRECTORIES:
        if path.exists():
            remove_managed_path(path)
            removed.append(path)
    for path in TEMPORARY_CACHE_DIRECTORIES:
        if path.exists():
            remove_temporary_path(path)
            removed.append(path)

    return removed


def open_latest_report() -> int:
    """最新の品質reportをOS既定のviewerで開く。"""
    reports = sorted(
        (ARTIFACT_ROOT / "quality" / "profiles").glob("*/current/report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        print("最新の品質reportがありません。先に品質検証を実行してください。", file=sys.stderr)
        return 2
    report = reports[0]
    if os.name == "nt":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            print("この環境では品質reportを開けません。", file=sys.stderr)
            return 1
        startfile(report)
    else:
        print(report)
    return 0


def cleanup_owned_resources(*, confirmation: str | None) -> int:
    """品質runnerが識別子で所有するDocker resourceだけを削除する。"""
    docker = shutil.which("docker")
    if docker is None:
        print("Docker CLIを確認できません。", file=sys.stderr)
        return 2
    environment = {**os.environ, "COMPOSE_PROJECT_NAME": QUALITY_COMPOSE_PROJECT_NAME}
    discovery = {
        "compose_containers": (
            docker,
            "ps",
            "--all",
            "--filter",
            f"label=com.docker.compose.project={QUALITY_COMPOSE_PROJECT_NAME}",
            "--format",
            "{{.ID}}\t{{.Names}}",
        ),
        "compose_volumes": (
            docker,
            "volume",
            "ls",
            "--filter",
            f"label=com.docker.compose.project={QUALITY_COMPOSE_PROJECT_NAME}",
            "--format",
            "{{.Name}}",
        ),
        "supabase_containers": (
            docker,
            "ps",
            "--all",
            "--filter",
            "label=com.supabase.cli.project",
            "--format",
            '{{.ID}}\t{{.Names}}\t{{.Label "com.supabase.cli.project"}}',
        ),
        "supabase_volumes": (
            docker,
            "volume",
            "ls",
            "--filter",
            "label=com.supabase.cli.project",
            "--format",
            '{{.Name}}\t{{.Label "com.supabase.cli.project"}}',
        ),
        "supabase_networks": (
            docker,
            "network",
            "ls",
            "--filter",
            "label=com.supabase.cli.project",
            "--format",
            '{{.ID}}\t{{.Name}}\t{{.Label "com.supabase.cli.project"}}',
        ),
    }
    outputs: dict[str, str] = {}
    for name, command in discovery.items():
        result = run_command(command, timeout_seconds=30, environment=environment)
        if result.returncode != 0:
            print(redact(result.output), file=sys.stderr)
            return 1
        outputs[name] = result.output
    compose_containers = _resource_rows(outputs["compose_containers"])
    compose_volumes = _resource_rows(outputs["compose_volumes"])
    supabase_containers = _quality_supabase_rows(outputs["supabase_containers"], fields=3)
    supabase_volumes = _quality_supabase_rows(outputs["supabase_volumes"], fields=2)
    supabase_networks = _quality_supabase_rows(outputs["supabase_networks"], fields=3)
    print("削除対象:")
    print(f"- Compose project: {QUALITY_COMPOSE_PROJECT_NAME}")
    _print_resource_rows("Compose container", compose_containers)
    _print_resource_rows("Compose volume", compose_volumes)
    _print_resource_rows("Supabase container", supabase_containers)
    _print_resource_rows("Supabase volume", supabase_volumes)
    _print_resource_rows("Supabase network", supabase_networks)
    if confirmation != QUALITY_RESOURCE_CONFIRMATION:
        print(f"削除する場合は--confirm {QUALITY_RESOURCE_CONFIRMATION}を指定してください。")
        return 2
    compose = run_command(
        (docker, "compose", "--profile", "e2e", "down", "--volumes", "--remove-orphans"),
        timeout_seconds=180,
        environment=environment,
    )
    if compose.returncode != 0:
        print(redact(compose.output), file=sys.stderr)
        return 1
    removals = (
        ("container", "rm", "--force", [row[0] for row in supabase_containers]),
        ("volume", "rm", "", [row[0] for row in supabase_volumes]),
        ("network", "rm", "", [row[0] for row in supabase_networks]),
    )
    for resource_type, action, option, identifiers in removals:
        if not identifiers:
            continue
        removal_command = [docker, action]
        if resource_type != "container":
            removal_command.insert(1, resource_type)
        if option:
            removal_command.append(option)
        removal_command.extend(identifiers)
        removed = run_command(
            tuple(removal_command),
            timeout_seconds=60,
            environment=environment,
        )
        if removed.returncode != 0:
            print(redact(removed.output), file=sys.stderr)
            return 1
    return 0


def _resource_rows(output: str) -> list[tuple[str, ...]]:
    return [
        tuple(part.strip() for part in line.split("\t")) for line in output.splitlines() if line
    ]


def _quality_supabase_rows(output: str, *, fields: int) -> list[tuple[str, ...]]:
    return [
        row
        for row in _resource_rows(output)
        if len(row) == fields and row[-1].startswith(services_gate.QUALITY_SUPABASE_PREFIX)
    ]


def _print_resource_rows(label: str, rows: list[tuple[str, ...]]) -> None:
    if not rows:
        print(f"- {label}: なし")
        return
    for row in rows:
        print(f"- {label}: {' / '.join(row)}")


def _run_gate(context: RunContext, gate: Gate) -> GateResult:
    from scripts.quality.reuse import gate_fingerprint

    log_path = context.run_dir / "logs" / f"{gate.name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as stream:
            previous_artifacts = _artifact_fingerprints(context, gate)
            if gate.action is not None:
                command_result = gate.action(context, log_path)
                stream.write(redact(command_result.output))
            else:
                command_result = run_command(
                    gate.command,
                    timeout_seconds=gate.timeout_seconds or context.timeout_seconds,
                    environment=context.environment,
                    output=stream,
                    cwd=gate.cwd,
                )
            artifact_issues, contract_artifacts = _artifact_contract(
                context,
                gate,
                previous_artifacts=previous_artifacts,
            )
            if command_result.returncode == 0 and artifact_issues:
                detail = "\n成果物契約に違反しています:\n" + "".join(
                    f"- {issue}\n" for issue in artifact_issues
                )
                stream.write(detail)
                command_result = CommandResult(
                    command_result.command,
                    1,
                    command_result.duration_seconds,
                    command_result.output + detail,
                    command_result.timed_out,
                )
            artifacts = (
                contract_artifacts
                if command_result.returncode == 0
                else _resolved_diagnostics(context, gate)
            )
        state = _command_state(command_result, nonzero_state=gate.nonzero_state)
        message = "timeout" if command_result.timed_out else None
        return GateResult(
            name=gate.name,
            description=gate.description,
            state=state,
            duration_seconds=command_result.duration_seconds,
            command=command_result.command,
            returncode=command_result.returncode,
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=message,
            artifacts=artifacts,
            fingerprint=gate_fingerprint(context, gate) if gate.reusable else None,
        )
    except EnvironmentBlockedError as error:
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        return GateResult(
            gate.name,
            gate.description,
            "blocked",
            time.monotonic() - started,
            command=list(gate.command),
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=redact(str(error)),
            artifacts=_resolved_diagnostics(context, gate),
        )
    except Exception as error:
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        return GateResult(
            gate.name,
            gate.description,
            "error",
            time.monotonic() - started,
            command=list(gate.command),
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=redact(str(error)),
            artifacts=_resolved_diagnostics(context, gate),
        )


def _artifact_contract(
    context: RunContext,
    gate: Gate,
    *,
    previous_artifacts: dict[Path, tuple[int, int, int, str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Gate自身が宣言した成果物の欠落と鮮度を検査する。"""
    issues: list[str] = []
    artifacts: list[str] = []
    seen_artifacts: set[str] = set()
    started = context.started_at.timestamp()
    for pattern in gate.artifacts:
        root = ARTIFACT_ROOT if pattern.startswith("outputs/") else context.run_dir
        matches = sorted(path for path in root.glob(pattern) if path.is_file())
        if not matches:
            issues.append(f"成果物がありません: {pattern}")
            continue
        for path in matches:
            artifact = _snapshot_artifact(path, context.run_dir)
            if artifact not in seen_artifacts:
                artifacts.append(artifact)
                seen_artifacts.add(artifact)
        if all(
            path.stat().st_mtime < started
            and (
                previous_artifacts is None
                or (
                    path in previous_artifacts
                    and _artifact_fingerprint(path) == previous_artifacts[path]
                )
            )
            for path in matches
        ):
            issues.append(f"成果物が現在runで更新されていません: {pattern}")
    return issues, artifacts


def _artifact_fingerprints(
    context: RunContext,
    gate: Gate,
) -> dict[Path, tuple[int, int, int, str]]:
    """Gate実行前に存在する宣言成果物の内容とmetadataを固定する."""
    fingerprints: dict[Path, tuple[int, int, int, str]] = {}
    for pattern in gate.artifacts:
        root = ARTIFACT_ROOT if pattern.startswith("outputs/") else context.run_dir
        for path in root.glob(pattern):
            if path.is_file() and path not in fingerprints:
                fingerprints[path] = _artifact_fingerprint(path)
    return fingerprints


def _artifact_fingerprint(path: Path) -> tuple[int, int, int, str]:
    """Filesystem時刻解像度に依存しない一つの成果物fingerprintを返す."""
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, digest


def _snapshot_artifact(path: Path, run_dir: Path) -> str:
    """共有build成果物をrun内へ固定し、後続runによる上書きを防ぐ。"""
    if path.is_relative_to(run_dir):
        return path.relative_to(run_dir).as_posix()
    relative = path.relative_to(ARTIFACT_ROOT)
    target = run_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return relative.as_posix()


def _resolved_diagnostics(context: RunContext, gate: Gate) -> list[str]:
    """失敗時にも保持するrun固有診断成果物を返す。"""
    return [
        path.relative_to(context.run_dir).as_posix()
        for pattern in gate.diagnostics
        for path in sorted(context.run_dir.glob(pattern))
        if path.is_file() and path.is_relative_to(context.run_dir)
    ]


def _command_state(result: CommandResult, *, nonzero_state: FailureState = "failed") -> State:
    """終了結果を品質違反と実行基盤異常へ分類する。"""
    if result.timed_out:
        return "error"
    if result.returncode == 0:
        return "passed"
    if _is_pytest_command(result.command) and result.returncode != 1:
        return "error"
    if result.returncode == 2:
        return "blocked"
    return nonzero_state


def _is_pytest_command(command: Sequence[str]) -> bool:
    """Python module形式のpytest commandか判定する。"""
    return any(
        tuple(command[index : index + 2]) == ("-m", "pytest")
        for index in range(max(0, len(command) - 1))
    )


def _skipped_gate_results(
    stages: Sequence[Sequence[Gate]],
    *,
    message: str,
    completed: set[str] | None = None,
) -> list[GateResult]:
    """未完了gateを機械可読なskipped結果へ変換する。"""
    completed = completed or set()
    return [
        GateResult(
            gate.name,
            gate.description,
            "skipped",
            0.0,
            command=list(gate.command),
            message=message,
        )
        for stage in stages
        for gate in stage
        if gate.name not in completed
    ]


def _record_runner_error(
    context: RunContext,
    results: list[GateResult],
    stages: Sequence[Sequence[Gate]],
    *,
    message: str,
) -> None:
    """runner内部異常を記録し、未完了gateを未検証として明示する。"""
    sanitized = redact(message)
    log_path = context.run_dir / "logs" / "runner.log"
    log_path.write_text(sanitized + "\n", encoding="utf-8")
    runner_result = GateResult(
        "runner",
        "Quality runner",
        "error",
        0.0,
        log=log_path.relative_to(context.run_dir).as_posix(),
        message=sanitized,
    )
    results.append(runner_result)
    _append_events(context.run_dir / "events.jsonl", [runner_result])
    skipped = _skipped_gate_results(
        stages,
        message="runnerが完了しなかったため検証結果を確定できませんでした。",
        completed={result.name for result in results},
    )
    results.extend(skipped)
    _append_events(context.run_dir / "events.jsonl", skipped)


def execute(
    profile: str,
    *,
    jobs: int,
    timeout_seconds: int,
    settings: QualitySettings | None = None,
    stages_override: list[list[Gate]] | None = None,
    selectors: Sequence[str] | None = None,
    fresh: bool = False,
    requested_profile: str | None = None,
    selection_reason: str = "",
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    change: ChangeSet | None = None,
) -> tuple[State, Path]:
    """指定profileのgateを段階ごとに並列実行する。"""
    from scripts.quality.retention import mark_run_active, recover_abandoned_runs

    recover_abandoned_runs()
    run_id, run_dir = create_run_directory(profile)
    mark_run_active(run_dir)
    environment = quality_environment(run_dir=run_dir)
    context = RunContext(
        profile=profile,
        jobs=jobs,
        timeout_seconds=timeout_seconds,
        run_id=run_id,
        run_dir=run_dir,
        environment=environment,
        started_at=utc_now(),
        change=change or ChangeSet(base_ref, None, "", None, ()),
        requested_profile=requested_profile or profile,
        selection_reason=selection_reason,
        fresh=fresh,
    )
    results: list[GateResult] = []
    event_path = run_dir / "events.jsonl"
    settings = settings or load_quality_settings()
    if selectors is not None:
        from scripts.quality.profiles import build_catalog
        from scripts.quality.scheduler import select_stages

        catalog_profile = "deep" if profile.startswith("gate-") else profile
        stages = select_stages(
            [
                build_catalog(
                    catalog_profile,
                    run_dir=run_dir,
                    settings=settings,
                    jobs=jobs,
                    fresh=fresh,
                )
            ],
            selectors,
        )
    else:
        stages = stages_override or _profile_stages(profile, jobs, run_dir, settings, fresh=fresh)
    context.environment_target = (
        "quality"
        if any(gate.environment_target == "quality" for stage in stages for gate in stage)
        else "python"
    )
    try:
        context.change = change or resolve_changes(base_ref, head_ref)
        context.initial_repository_snapshot = capture_snapshot()
        context.initial_dependency_fingerprint = python_installation_fingerprint()
    except KeyboardInterrupt:
        message = "品質実行が初期化中に中断されました。"
        log_path = run_dir / "logs" / "runner-setup.log"
        log_path.write_text(message + "\n", encoding="utf-8")
        result = GateResult(
            "runner-setup",
            "Quality runner setup",
            "error",
            0.0,
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=message,
        )
        results.append(result)
        results.extend(
            _skipped_gate_results(
                stages,
                message="runnerの初期化が完了しなかったため実行しませんでした。",
            )
        )
        _append_events(event_path, results)
        state, _report_path = _write_summary(context, results)
        redact_artifacts(run_dir)
        from scripts.quality.retention import publish_run

        return state, publish_run(run_dir, context.profile, state)
    except EnvironmentBlockedError as error:
        log_path = run_dir / "logs" / "runner-setup.log"
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        result = GateResult(
            "runner-setup",
            "Quality runner setup",
            "blocked",
            0.0,
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=redact(str(error)),
        )
        results.append(result)
        results.extend(
            _skipped_gate_results(
                stages,
                message="runnerの初期化が完了しなかったため実行しませんでした。",
            )
        )
        _append_events(event_path, results)
        state, _report_path = _write_summary(context, results)
        redact_artifacts(run_dir)
        from scripts.quality.retention import publish_run

        return state, publish_run(run_dir, context.profile, state)
    except Exception as error:
        log_path = run_dir / "logs" / "runner-setup.log"
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        result = GateResult(
            "runner-setup",
            "Quality runner setup",
            "error",
            0.0,
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=redact(str(error)),
        )
        results.append(result)
        results.extend(
            _skipped_gate_results(
                stages,
                message="runnerの初期化が完了しなかったため実行しませんでした。",
            )
        )
        _append_events(event_path, results)
        state, _report_path = _write_summary(context, results)
        redact_artifacts(run_dir)
        from scripts.quality.retention import publish_run

        return state, publish_run(run_dir, context.profile, state)

    gate_states: dict[str, State] = {}
    try:
        for stage in stages:
            runnable: list[Gate] = []
            skipped: list[GateResult] = []
            for gate in stage:
                unavailable = [
                    dependency
                    for dependency in gate.dependencies
                    if gate_states.get(dependency) != "passed"
                ]
                if unavailable:
                    skipped.append(
                        GateResult(
                            gate.name,
                            gate.description,
                            "skipped",
                            0.0,
                            command=list(gate.command),
                            message=(
                                "依存gateが完了しなかったため実行しませんでした: "
                                + ", ".join(unavailable)
                            ),
                        )
                    )
                else:
                    from scripts.quality.reuse import reuse_gate

                    reused = reuse_gate(context, gate)
                    if reused is None:
                        runnable.append(gate)
                    else:
                        skipped.append(reused)
            if skipped:
                results.extend(skipped)
                gate_states.update({result.name: result.state for result in skipped})
                _append_events(event_path, skipped)
            if not runnable:
                continue
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(jobs, len(runnable))
            ) as executor:
                stage_results = list(executor.map(lambda gate: _run_gate(context, gate), runnable))
            results.extend(stage_results)
            gate_states.update({result.name: result.state for result in stage_results})
            redact_artifacts(run_dir)
            _append_events(event_path, stage_results)
    except KeyboardInterrupt:
        _record_runner_error(
            context,
            results,
            stages,
            message="品質実行が中断されました。",
        )
    except Exception as error:
        _record_runner_error(
            context,
            results,
            stages,
            message=(
                f"品質runnerがgate結果を確定できませんでした: {type(error).__name__}: {error}"
            ),
        )
    finally:
        supabase_lease = context.resources.get("supabase")
        if supabase_lease is not None and supabase_lease.cleanup_required:
            stopped = _run_gate(
                context,
                Gate(
                    "supabase-stop",
                    "Stop quality-owned Supabase",
                    action=services_gate.stop_supabase,
                    timeout_seconds=60,
                    nonzero_state="error",
                ),
            )
            results.append(stopped)
            _append_events(event_path, [stopped])

    repository_stability = _repository_stability_result(context)
    results.append(repository_stability)
    _append_events(event_path, [repository_stability])
    stability = _environment_stability_result(context)
    results.append(stability)
    _append_events(event_path, [stability])
    process_stability = _process_stability_result(context)
    results.append(process_stability)
    _append_events(event_path, [process_stability])

    state, _report_path = _write_summary(context, results)
    redact_artifacts(run_dir)
    from scripts.quality.retention import publish_run

    return state, publish_run(run_dir, context.profile, state)


def _repository_stability_result(context: RunContext) -> GateResult:
    """品質実行全体がrepository状態を変更していないことを返す。"""
    started = time.monotonic()
    log_path = context.run_dir / "logs" / "repository-stability.log"
    try:
        current = capture_snapshot()
        changed = current != context.initial_repository_snapshot
        message = "品質実行によりrepository状態が変更されました。" if changed else None
        log_path.write_text((message or "Repository状態は不変です。") + "\n", encoding="utf-8")
        return GateResult(
            "repository-stability",
            "Repository state unchanged",
            "failed" if changed else "passed",
            time.monotonic() - started,
            command=["git-repository-snapshot"],
            returncode=1 if changed else 0,
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=message,
        )
    except (OSError, RuntimeError) as error:
        message = f"Repository状態を再確認できません: {error}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return GateResult(
            "repository-stability",
            "Repository state unchanged",
            "error",
            time.monotonic() - started,
            command=["git-repository-snapshot"],
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=message,
        )


def _environment_stability_result(context: RunContext) -> GateResult:
    """品質実行がPython依存環境を変更していないことを返す。"""
    started = time.monotonic()
    log_path = context.run_dir / "logs" / "environment-stability.log"
    try:
        current = python_installation_fingerprint()
        changed = current != context.initial_dependency_fingerprint
        message = "品質実行によりPython依存環境が変更されました。" if changed else None
        log_path.write_text((message or "Python依存環境は不変です。") + "\n", encoding="utf-8")
        return GateResult(
            "environment-stability",
            "Dependency environment unchanged",
            "failed" if changed else "passed",
            time.monotonic() - started,
            command=["python-installation-fingerprint"],
            returncode=1 if changed else 0,
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=message,
        )
    except (OSError, ValueError) as error:
        message = f"Python依存環境を再確認できません: {error}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return GateResult(
            "environment-stability",
            "Dependency environment unchanged",
            "error",
            time.monotonic() - started,
            command=["python-installation-fingerprint"],
            log=log_path.relative_to(context.run_dir).as_posix(),
            message=message,
        )


def _process_stability_result(context: RunContext) -> GateResult:
    """品質runnerが起動した子processを残していないことを検査する。"""
    started = time.monotonic()
    log_path = context.run_dir / "logs" / "process-stability.log"
    children = [child for child in psutil.Process().children(recursive=True) if child.is_running()]
    if children:
        identities = [f"{child.pid}:{child.name()}" for child in children]
        message = "品質所有processが残っています: " + ", ".join(identities)
        state: State = "error"
    else:
        message = "品質所有processは残っていません。"
        state = "passed"
    log_path.write_text(message + "\n", encoding="utf-8")
    return GateResult(
        "process-stability",
        "Quality-owned processes stopped",
        state,
        time.monotonic() - started,
        command=["psutil.Process.children"],
        returncode=0 if state == "passed" else 1,
        log=log_path.relative_to(context.run_dir).as_posix(),
        message=None if state == "passed" else message,
    )


def build_parser(settings: QualitySettings | None = None) -> argparse.ArgumentParser:
    """コマンドライン引数を構築する。"""
    settings = settings or load_quality_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("auto", *PROFILE_ORDER, "clean"))
    parser.add_argument(
        "--jobs",
        type=lambda value: _bounded_positive_int(value, maximum=settings.max_jobs),
        default=_default_jobs(settings),
    )
    parser.add_argument("--timeout", type=_positive_int)
    parser.add_argument("--confirm-deep", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    return parser


def _positive_int(value: str) -> int:
    """1以上の整数をargparse向けに検証する。"""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください。")
    return parsed


def _bounded_positive_int(value: str, *, maximum: int) -> int:
    """設定された上限以下の正整数をargparse向けに検証する。"""
    parsed = _positive_int(value)
    if parsed > maximum:
        raise argparse.ArgumentTypeError(f"{maximum}以下の整数を指定してください。")
    return parsed


def _default_jobs(settings: QualitySettings) -> int:
    """hostのCPU数を超えない既定並列数を返す。"""
    return min(settings.default_jobs, os.cpu_count() or 1)


def main(argv: Sequence[str] | None = None) -> int:
    """品質profileまたはcleanupを実行する。"""
    raw_arguments = list(argv) if argv is not None else sys.argv[1:]
    if raw_arguments and raw_arguments[0] == "report":
        parser = argparse.ArgumentParser(description="品質reportを操作します。")
        parser.add_argument("command", choices=("report",))
        parser.add_argument("action", choices=("open",))
        parser.parse_args(raw_arguments)
        return open_latest_report()
    if raw_arguments and raw_arguments[0] == "cleanup":
        parser = argparse.ArgumentParser(description="品質所有resourceを削除します。")
        parser.add_argument("command", choices=("cleanup",))
        parser.add_argument("--confirm")
        cleanup_arguments = parser.parse_args(raw_arguments)
        return cleanup_owned_resources(confirmation=cleanup_arguments.confirm)
    try:
        settings = load_quality_settings()
    except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
        print(f"品質設定を読み込めません: {error}", file=sys.stderr)
        return 2
    if raw_arguments and raw_arguments[0] == "list":
        from scripts.quality.profiles import GROUPS

        gates = {
            gate.name
            for stage in _profile_stages("deep", settings.max_jobs, settings=settings)
            for gate in stage
            if gate.name != "cleanup"
        }
        print("意味単位:")
        for name, members in sorted(GROUPS.items()):
            print(f"  {name}: {', '.join(members)}")
        print("個別gate:")
        for name in sorted(gates):
            print(f"  {name}")
        return 0
    if raw_arguments and raw_arguments[0] == "gate":
        parser = argparse.ArgumentParser(description="選択した品質gateを実行します。")
        parser.add_argument("command")
        parser.add_argument("selectors", nargs="+")
        parser.add_argument(
            "--jobs",
            type=lambda value: _bounded_positive_int(value, maximum=settings.max_jobs),
            default=_default_jobs(settings),
        )
        parser.add_argument("--timeout", type=_positive_int, default=settings.timeouts["check"])
        arguments = parser.parse_args(raw_arguments)
        selector_label = "-".join(arguments.selectors)
        try:
            state, report_path = execute(
                f"gate-{selector_label}",
                jobs=arguments.jobs,
                timeout_seconds=arguments.timeout,
                settings=settings,
                selectors=arguments.selectors,
                requested_profile="gate",
                selection_reason="個別selectorを明示指定しました: "
                + ", ".join(arguments.selectors),
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        print(f"判定: {state}")
        print(f"レポート: {report_path}")
        if state == "passed":
            return 0
        return 2 if state in {"blocked", "error"} else 1

    arguments = build_parser(settings).parse_args(raw_arguments)
    if arguments.profile == "clean":
        try:
            removed = clean()
        except (OSError, ValueError) as error:
            print(f"成果物を削除できません: {error}", file=sys.stderr)
            return 2
        print(f"{len(removed)}件の再生成可能な成果物を削除しました。")
        return 0
    requested_profile = arguments.profile
    selectors: Sequence[str] | None = None
    impact_reason = "profileを明示指定しました。"
    change: ChangeSet | None = None
    try:
        change = resolve_changes(arguments.base_ref, arguments.head_ref)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    if arguments.profile == "auto":
        from scripts.quality.impact import decide

        decision = decide(change.changed_paths)
        arguments.profile = decision.profile
        selectors = decision.selectors or None
        impact_reason = decision.reason
    if arguments.profile == "deep" and not arguments.confirm_deep:
        print("deepの実行には--confirm-deepが必要です。", file=sys.stderr)
        return 2
    timeout = arguments.timeout or settings.timeouts[arguments.profile]
    if arguments.explain:
        from scripts.quality.profiles import build_catalog
        from scripts.quality.scheduler import select_stages

        print(f"profile: {arguments.profile}")
        print(f"選定理由: {impact_reason}")
        explanation_stages = (
            select_stages(
                [
                    build_catalog(
                        arguments.profile,
                        run_dir=TEMPORARY_ROOT / "quality" / "runs" / "explain",
                        settings=settings,
                        jobs=arguments.jobs,
                        fresh=arguments.fresh,
                    )
                ],
                selectors,
            )
            if selectors is not None
            else _profile_stages(
                arguments.profile,
                arguments.jobs,
                settings=settings,
                fresh=arguments.fresh,
            )
        )
        for stage_index, stage in enumerate(explanation_stages, start=1):
            print(f"stage {stage_index}: {', '.join(gate.name for gate in stage)}")
        reusable = sorted(
            gate.name for stage in explanation_stages for gate in stage if gate.reusable
        )
        if arguments.fresh:
            print("再利用: --fresh指定のため無効")
        elif reusable:
            print("再利用候補: " + ", ".join(reusable))
        else:
            print("再利用候補: なし")
        return 0
    try:
        if arguments.profile in {"release", "deep"}:
            lock_path = Path(tempfile.gettempdir()) / "werewolf-agent-quality-release.lock"
            with exclusive_file_lock(lock_path, timeout_seconds=1):
                state, report_path = execute(
                    arguments.profile,
                    jobs=arguments.jobs,
                    timeout_seconds=timeout,
                    settings=settings,
                    selectors=selectors,
                    fresh=arguments.fresh,
                    requested_profile=requested_profile,
                    selection_reason=impact_reason,
                    base_ref=arguments.base_ref,
                    head_ref=arguments.head_ref,
                    change=change,
                )
        else:
            state, report_path = execute(
                arguments.profile,
                jobs=arguments.jobs,
                timeout_seconds=timeout,
                settings=settings,
                selectors=selectors,
                fresh=arguments.fresh,
                requested_profile=requested_profile,
                selection_reason=impact_reason,
                base_ref=arguments.base_ref,
                head_ref=arguments.head_ref,
                change=change,
            )
    except LockTimeoutError:
        print("release/deepのhost排他lockを取得できませんでした。", file=sys.stderr)
        return 2
    print(f"判定: {state}")
    print(f"レポート: {report_path}")
    if state == "passed":
        return 0
    if state in {"blocked", "error"}:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
