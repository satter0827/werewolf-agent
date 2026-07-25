"""ローカルとCIで共有する品質ゲート。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import shutil
import sys
import tarfile
import time
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

from scripts._support import (
    ARTIFACT_ROOT,
    OFFLINE_GUARD_ENVIRONMENT,
    QUALITY_ROOT,
    REPOSITORY_ROOT,
    TEMPORARY_CACHE_DIRECTORIES,
    TEMPORARY_ROOT,
    CommandResult,
    EnvironmentBlockedError,
    create_run_directory,
    prepare_temporary_directories,
    quality_environment,
    redact,
    redact_artifacts,
    remove_managed_path,
    remove_temporary_path,
    run_command,
    utc_now,
    write_json,
    write_latest,
)
from scripts.e2e import run_e2e
from scripts.preflight_supabase import isolated_project_id, prepare_supabase

State = Literal["passed", "failed", "error", "blocked", "skipped"]
FailureState = Literal["failed", "error", "blocked"]
Action = Callable[["RunContext", Path], CommandResult]

PROFILE_ORDER = ("quick", "check", "release", "deep")
BUILD_DIRECTORIES = (
    ARTIFACT_ROOT / "build",
    ARTIFACT_ROOT / "coverage",
    ARTIFACT_ROOT / "cache" / "mypy",
    ARTIFACT_ROOT / "cache" / "pytest",
    ARTIFACT_ROOT / "cache" / "ruff",
    ARTIFACT_ROOT / "cache" / "sphinx",
)


@dataclass(frozen=True, slots=True)
class QualitySettings:
    """pyproject.tomlから読む品質runner設定。"""

    max_jobs: int
    retention_days: int
    benchmark_min_rounds: int
    benchmark_max_mean_ms: int
    coverage_fail_under: int
    branch_coverage_fail_under: int
    timeouts: dict[str, int]


def load_quality_settings() -> QualitySettings:
    """品質設定をpyproject.tomlから検証して読み込む。"""
    document = _load_pyproject()
    tool = _required_table(document, "tool", "tool")
    quality = _required_table(tool, "werewolf-quality", "tool.werewolf-quality")
    timeouts = _required_table(quality, "timeouts", "tool.werewolf-quality.timeouts")
    coverage = _required_table(tool, "coverage", "tool.coverage")
    coverage_report = _required_table(coverage, "report", "tool.coverage.report")
    return QualitySettings(
        max_jobs=_required_int(quality, "max_jobs", minimum=1),
        retention_days=_required_int(quality, "retention_days", minimum=0),
        benchmark_min_rounds=_required_int(quality, "benchmark_min_rounds", minimum=1),
        benchmark_max_mean_ms=_required_int(
            quality,
            "benchmark_max_mean_ms",
            minimum=1,
        ),
        coverage_fail_under=_required_int(
            coverage_report,
            "fail_under",
            minimum=0,
            maximum=100,
        ),
        branch_coverage_fail_under=_required_int(
            quality,
            "branch_coverage_fail_under",
            minimum=0,
            maximum=100,
        ),
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


@dataclass(frozen=True, slots=True)
class Gate:
    """単一の品質判定。"""

    name: str
    description: str
    command: tuple[str, ...] = ()
    cwd: Path = REPOSITORY_ROOT
    action: Action | None = None
    timeout_seconds: int | None = None
    nonzero_state: FailureState = "failed"


@dataclass(slots=True)
class GateResult:
    """単一gateのレポート。"""

    name: str
    description: str
    state: State
    duration_seconds: float
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    log: str | None = None
    message: str | None = None


@dataclass(slots=True)
class RunContext:
    """1回の品質実行で共有する状態。"""

    profile: str
    jobs: int
    timeout_seconds: int
    run_id: str
    run_dir: Path
    environment: dict[str, str]
    initial_git_status: str
    started_at: datetime
    supabase_environment: dict[str, str] = field(default_factory=dict)
    supabase_cleanup_required: bool = False
    supabase_workdir: Path | None = None
    supabase_project_id: str | None = None


def _python(*arguments: str) -> tuple[str, ...]:
    return (sys.executable, *arguments)


def _python_tool(name: str) -> tuple[str, ...]:
    suffix = ".exe" if os.name == "nt" else ""
    return (str(Path(sys.executable).parent / f"{name}{suffix}"),)


def _npm(*arguments: str) -> tuple[str, ...]:
    executable = shutil.which("npm") or "npm"
    return (executable, *arguments)


def _git_status(environment: dict[str, str]) -> str:
    result = run_command(
        ["git", "status", "--porcelain=v1"],
        timeout_seconds=30,
        environment=environment,
    )
    if result.timed_out:
        raise RuntimeError("Git working treeの確認がtimeoutしました。")
    if result.returncode != 0:
        raise RuntimeError("Git working treeの状態を取得できませんでした。")
    return result.output


def _clean_tree_action(context: RunContext, _: Path) -> CommandResult:
    started = time.monotonic()
    current = _git_status(context.environment)
    if current == context.initial_git_status:
        return CommandResult(["git", "status", "--porcelain=v1"], 0, time.monotonic() - started, "")
    return CommandResult(
        ["git", "status", "--porcelain=v1"],
        1,
        time.monotonic() - started,
        "品質実行によりtracked fileが変更されました。\n" + current,
    )


def _supabase_action(context: RunContext, _: Path) -> CommandResult:
    started = time.monotonic()
    isolated_root = ARTIFACT_ROOT / "db" / "quality" / context.run_id
    context.supabase_cleanup_required = True
    context.supabase_workdir = isolated_root
    context.supabase_project_id = isolated_project_id(isolated_root)
    preflight = prepare_supabase(
        timeout_seconds=min(context.timeout_seconds, 180),
        isolated_root=isolated_root,
        base_environment=context.environment,
    )
    context.supabase_environment = preflight.environment
    context.supabase_cleanup_required = preflight.workdir is not None
    context.supabase_workdir = preflight.workdir
    context.supabase_project_id = preflight.project_id
    context.environment.update(context.supabase_environment)
    return CommandResult(
        ["python", "-m", "scripts.preflight_supabase"],
        0,
        time.monotonic() - started,
        "ローカルSupabaseの準備が完了しました。\n",
    )


def _supabase_stop_action(context: RunContext, _: Path) -> CommandResult:
    """品質用Supabaseと一時projectを停止・削除する。"""
    started = time.monotonic()
    command = ["supabase", "stop", "--no-backup"]
    if context.supabase_project_id is not None:
        command.extend(["--project-id", context.supabase_project_id])
    if context.supabase_workdir is not None:
        command.extend(["--workdir", str(context.supabase_workdir)])
        if not context.supabase_workdir.exists():
            result = CommandResult(
                command,
                0,
                time.monotonic() - started,
                "品質用Supabaseは既に停止・削除されています。\n",
            )
        else:
            result = run_command(
                command,
                timeout_seconds=60,
                environment=context.environment,
            )
    else:
        result = run_command(
            command,
            timeout_seconds=60,
            environment=context.environment,
        )
    try:
        if (
            result.returncode == 0
            and context.supabase_workdir is not None
            and context.supabase_workdir.exists()
        ):
            remove_managed_path(context.supabase_workdir)
    finally:
        supabase_home = context.environment.get("SUPABASE_HOME")
        if supabase_home:
            profile = Path(supabase_home)
            if profile.exists():
                remove_temporary_path(profile)
    return CommandResult(
        command,
        result.returncode,
        time.monotonic() - started,
        result.output,
        result.timed_out,
    )


def _cleanup_action(context: RunContext, _: Path) -> CommandResult:
    started = time.monotonic()
    try:
        removed = clean()
        prepare_temporary_directories()
    except PermissionError as error:
        raise EnvironmentBlockedError("再生成可能な成果物を削除できませんでした。") from error
    return CommandResult(
        ["python", "-m", "scripts.quality", "clean"],
        0,
        time.monotonic() - started,
        f"{len(removed)}件の再生成可能な成果物を削除しました。\n",
    )


def _package_action(context: RunContext, _: Path) -> CommandResult:
    """配布物を再構築し、公開entrypointと全resourceを検査する。"""
    started = time.monotonic()
    output_directory = ARTIFACT_ROOT / "build" / "package"
    if output_directory.exists():
        remove_managed_path(output_directory)
    command = _package_command(output_directory)
    built = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    output = [built.output]
    if built.returncode != 0:
        return built

    errors = _distribution_contract_errors(output_directory)
    if errors:
        output.append("\n配布物契約に違反しています:\n")
        output.extend(f"- {error}\n" for error in errors)
        return CommandResult(
            command=list(command),
            returncode=1,
            duration_seconds=time.monotonic() - started,
            output="".join(output),
        )
    output.append("\n配布物のentrypointと全resourceを確認しました。\n")
    return CommandResult(
        command=list(command),
        returncode=0,
        duration_seconds=time.monotonic() - started,
        output="".join(output),
    )


def _docs_action(context: RunContext, _: Path) -> CommandResult:
    """既存出力を除去してSphinx成果物を現在runで再構築する。"""
    output_directory = ARTIFACT_ROOT / "build" / "docs"
    if output_directory.exists():
        remove_managed_path(output_directory)
    command = _docs_command(context.run_dir)
    return run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )


def _docs_command(run_dir: Path) -> tuple[str, ...]:
    """Sphinx warning-as-error buildの固定commandを返す。"""
    return _python(
        "-m",
        "sphinx",
        "-W",
        "--keep-going",
        "-b",
        "html",
        "-d",
        str(TEMPORARY_ROOT / "sphinx" / run_dir.name),
        "-c",
        "docs/sphinx",
        "docs",
        str(ARTIFACT_ROOT / "build" / "docs"),
    )


def _openapi_action(context: RunContext, _: Path) -> CommandResult:
    """OpenAPIと生成したTypeScript型をtracked契約と比較する。"""
    started = time.monotonic()
    generated = context.run_dir / "contracts" / "openapi.json"
    generated_types = context.run_dir / "contracts" / "api.ts"
    command = _python("-m", "scripts.export_openapi", "--output", str(generated))
    result = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if result.returncode != 0:
        return result
    frontend_directory = REPOSITORY_ROOT / "frontend"
    relative_schema = os.path.relpath(generated, frontend_directory)
    relative_types = os.path.relpath(generated_types, frontend_directory)
    type_command = _npm(
        "exec",
        "--offline",
        "--",
        "openapi-typescript",
        relative_schema,
        "-o",
        relative_types,
    )
    type_result = run_command(
        type_command,
        cwd=frontend_directory,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if type_result.returncode != 0:
        return type_result
    expected = REPOSITORY_ROOT / "openapi.json"
    expected_types = REPOSITORY_ROOT / "frontend" / "src" / "generated" / "api.ts"
    matches = (
        expected.is_file()
        and expected_types.is_file()
        and generated.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")
        and generated_types.read_text(encoding="utf-8")
        == expected_types.read_text(encoding="utf-8")
    )
    output = result.output + type_result.output
    if not matches:
        output += "生成したOpenAPI契約またはTypeScript型がtracked契約と一致しません。\n"
    return CommandResult(
        command=list(command),
        returncode=0 if matches else 1,
        duration_seconds=time.monotonic() - started,
        output=output,
    )


def _package_command(output_directory: Path) -> tuple[str, ...]:
    """配布物を構築する固定commandを返す。"""
    return _python(
        "-m",
        "build",
        "--no-isolation",
        "--outdir",
        str(output_directory),
    )


def _distribution_contract_errors(output_directory: Path) -> list[str]:
    """構築済みwheelとsdistの公開契約違反を返す。"""
    packaged_resources, console_entrypoints = _distribution_contract()
    wheels = sorted(output_directory.glob("*.whl"))
    source_distributions = sorted(output_directory.glob("*.tar.gz"))
    errors: list[str] = []
    if len(wheels) != 1:
        errors.append(f"wheelは1件必要です: {len(wheels)}件")
    if len(source_distributions) != 1:
        errors.append(f"sdistは1件必要です: {len(source_distributions)}件")
    elif source_distributions:
        errors.extend(_sdist_contract_errors(source_distributions[0]))
    if len(wheels) != 1:
        return errors

    try:
        with ZipFile(wheels[0]) as wheel:
            names = set(wheel.namelist())
            entrypoint_files = sorted(
                name for name in names if name.endswith(".dist-info/entry_points.txt")
            )
            if len(entrypoint_files) != 1:
                errors.append(f"entry_points.txtは1件必要です: {len(entrypoint_files)}件")
                metadata = ""
            else:
                metadata = wheel.read(entrypoint_files[0]).decode("utf-8")
    except (BadZipFile, OSError, UnicodeDecodeError) as error:
        errors.append(f"wheelを読み取れません: {error}")
        return errors

    errors.extend(
        f"resourceがありません: {resource}"
        for resource in packaged_resources
        if resource not in names
    )
    errors.extend(
        f"console entrypointがありません: {entrypoint}"
        for entrypoint in console_entrypoints
        if entrypoint not in metadata
    )
    return errors


def _sdist_contract_errors(source_distribution: Path) -> list[str]:
    """sdistが設定された公開sourceを読める形で含むか検査する。"""
    try:
        with tarfile.open(source_distribution, mode="r:gz") as archive:
            names = {name.split("/", maxsplit=1)[1] for name in archive.getnames() if "/" in name}
    except (tarfile.TarError, OSError) as error:
        return [f"sdistを読み取れません: {error}"]

    errors: list[str] = []
    for source in _sdist_contract():
        path = REPOSITORY_ROOT / source
        present = (
            source in names
            if path.is_file()
            else any(name.startswith(f"{source}/") for name in names)
        )
        if not present:
            errors.append(f"sdist sourceがありません: {source}")
    return errors


def _sdist_contract() -> tuple[str, ...]:
    """pyproject.tomlからsdistに含めるsource契約を返す。"""
    document = _load_pyproject()
    tool = _required_table(document, "tool", "tool")
    hatch = _required_table(tool, "hatch", "tool.hatch")
    build = _required_table(hatch, "build", "tool.hatch.build")
    targets = _required_table(build, "targets", "tool.hatch.build.targets")
    sdist = _required_table(targets, "sdist", "tool.hatch.build.targets.sdist")
    only_include = sdist.get("only-include")
    if not isinstance(only_include, list) or not all(
        isinstance(value, str) and value for value in only_include
    ):
        raise ValueError("sdist.only-includeは空でない文字列の配列で指定してください。")
    return tuple(sorted(only_include))


def _distribution_contract() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """pyproject.tomlからwheelのresourceとentrypoint契約を返す。"""
    document = _load_pyproject()
    tool = _required_table(document, "tool", "tool")
    hatch = _required_table(tool, "hatch", "tool.hatch")
    build = _required_table(hatch, "build", "tool.hatch.build")
    targets = _required_table(build, "targets", "tool.hatch.build.targets")
    wheel = _required_table(targets, "wheel", "tool.hatch.build.targets.wheel")
    force_include = _required_table(
        wheel,
        "force-include",
        "tool.hatch.build.targets.wheel.force-include",
    )
    project = _required_table(document, "project", "project")
    scripts = _required_table(project, "scripts", "project.scripts")
    if not all(isinstance(value, str) for value in force_include.values()):
        raise ValueError("wheel.force-includeの保存先は文字列で指定してください。")
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in scripts.items()):
        raise ValueError("project.scriptsは文字列の名前と参照先で指定してください。")
    resources = tuple(sorted(str(value) for value in force_include.values()))
    entrypoints = tuple(sorted(f"{name} = {value}" for name, value in scripts.items()))
    return resources, entrypoints


def _benchmark_action(
    context: RunContext,
    _: Path,
    *,
    settings: QualitySettings,
) -> CommandResult:
    """Core benchmarkを実行し、設定された性能上限を検査する。"""
    started = time.monotonic()
    result_path = context.run_dir / "benchmarks" / "core.json"
    command = _benchmark_command(context.run_dir, settings)
    benchmark = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if benchmark.returncode != 0:
        return benchmark

    errors, measurements = _benchmark_contract(
        result_path,
        maximum_mean_ms=settings.benchmark_max_mean_ms,
    )
    output = [benchmark.output]
    output.extend(f"{name}: mean={mean_ms:.3f}ms\n" for name, mean_ms in measurements)
    if errors:
        output.append("benchmark契約に違反しています:\n")
        output.extend(f"- {error}\n" for error in errors)
        return CommandResult(
            command=command,
            returncode=1,
            duration_seconds=time.monotonic() - started,
            output="".join(output),
        )
    return CommandResult(
        command=command,
        returncode=0,
        duration_seconds=time.monotonic() - started,
        output="".join(output),
    )


def _coverage_action(
    context: RunContext,
    _: Path,
    *,
    settings: QualitySettings,
) -> CommandResult:
    """総合coverageとbranch rateをそれぞれの下限で検査する。"""
    started = time.monotonic()
    command = _coverage_command(context.run_dir, settings)
    coverage = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if coverage.returncode != 0:
        return coverage

    errors, branch_percentage = _branch_coverage_contract(
        context.run_dir / "coverage" / "coverage.xml",
        minimum_percentage=settings.branch_coverage_fail_under,
    )
    output = [coverage.output]
    if branch_percentage is not None:
        output.append(
            "branch coverage: "
            f"{branch_percentage:.2f}% "
            f"(下限 {settings.branch_coverage_fail_under}%)\n"
        )
    if errors:
        output.append("branch coverage契約に違反しています:\n")
        output.extend(f"- {error}\n" for error in errors)
    return CommandResult(
        command=command,
        returncode=1 if errors else 0,
        duration_seconds=time.monotonic() - started,
        output="".join(output),
    )


def _coverage_command(run_dir: Path, settings: QualitySettings) -> list[str]:
    """Coverage成果物を同じrunへ保存するpytest commandを返す。"""
    return list(
        _python(
            "-m",
            "pytest",
            "--test-level=check",
            "-m",
            "not benchmark",
            "--cov=werewolf_agent",
            "--cov-branch",
            "--cov-report",
            f"xml:{run_dir / 'coverage' / 'coverage.xml'}",
            "--cov-report",
            f"html:{run_dir / 'coverage' / 'html'}",
            f"--cov-fail-under={settings.coverage_fail_under}",
            "--junitxml",
            str(run_dir / "test-results" / "coverage.xml"),
            "tests/unit",
        )
    )


def _branch_coverage_contract(
    result_path: Path,
    *,
    minimum_percentage: int,
) -> tuple[list[str], float | None]:
    """Coverage XMLからbranch rateを読み、設定下限との違反を返す。"""
    try:
        root = ET.parse(result_path).getroot()
        rate = float(root.attrib["branch-rate"])
    except (ET.ParseError, KeyError, OSError, ValueError) as error:
        return [f"coverage XMLのbranch-rateを読み取れません: {error}"], None
    if not 0 <= rate <= 1:
        return [f"branch-rateが範囲外です: {rate}"], None
    percentage = rate * 100
    if percentage < minimum_percentage:
        return [
            f"branch coverage {percentage:.2f}% は下限 {minimum_percentage}% を下回っています。"
        ], percentage
    return [], percentage


def _benchmark_command(run_dir: Path, settings: QualitySettings) -> list[str]:
    """Core benchmarkの固定commandを返す。"""
    return list(
        _python(
            "-m",
            "pytest",
            "--test-level=check",
            "-m",
            "benchmark",
            "-n",
            "0",
            "--benchmark-disable-gc",
            f"--benchmark-min-rounds={settings.benchmark_min_rounds}",
            "--benchmark-json",
            str(run_dir / "benchmarks" / "core.json"),
            "--junitxml",
            str(run_dir / "test-results" / "benchmark.xml"),
            "tests/unit/domain",
        )
    )


def _benchmark_contract(
    result_path: Path,
    *,
    maximum_mean_ms: int,
) -> tuple[list[str], list[tuple[str, float]]]:
    """Benchmark JSONの構造と平均実行時間を検査する。"""
    try:
        document = json.loads(result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return [f"結果JSONを読み取れません: {error}"], []
    benchmarks = document.get("benchmarks") if isinstance(document, dict) else None
    if not isinstance(benchmarks, list) or not benchmarks:
        return ["benchmark結果がありません。"], []

    errors: list[str] = []
    measurements: list[tuple[str, float]] = []
    for index, benchmark in enumerate(benchmarks):
        if not isinstance(benchmark, dict):
            errors.append(f"benchmark[{index}]がobjectではありません。")
            continue
        name = benchmark.get("name")
        stats = benchmark.get("stats")
        mean = stats.get("mean") if isinstance(stats, dict) else None
        if (
            not isinstance(name, str)
            or isinstance(mean, bool)
            or not isinstance(mean, (int, float))
        ):
            errors.append(f"benchmark[{index}]のnameまたはmeanが不正です。")
            continue
        mean_ms = float(mean) * 1000
        measurements.append((name, mean_ms))
        if mean_ms > maximum_mean_ms:
            errors.append(f"{name}の平均{mean_ms:.3f}msが上限{maximum_mean_ms}msを超えました。")
    return errors, measurements


_RUNTIME_IMAGE = "werewolf-agent-quality-runtime:latest"


def _docker_commands(image: str) -> tuple[list[str], ...]:
    """事前構築済みruntime imageの非root・entrypoint smokeを返す。"""
    return (
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            image,
            "-c",
            "import os, werewolf_agent; assert os.geteuid() != 0",
        ],
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "werewolf-agent-worker",
            image,
            "--help",
        ],
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "werewolf-agent",
            image,
            "--help",
        ],
    )


def _docker_action(context: RunContext, _: Path) -> CommandResult:
    started = time.monotonic()
    if shutil.which("docker") is None:
        raise EnvironmentBlockedError("Docker CLIが見つかりません。")
    docker_info = run_command(
        ["docker", "info"],
        timeout_seconds=30,
        environment=context.environment,
    )
    if docker_info.returncode != 0:
        raise EnvironmentBlockedError("Docker engineが起動していません。")
    image_check = run_command(
        ["docker", "image", "inspect", _RUNTIME_IMAGE],
        timeout_seconds=30,
        environment=context.environment,
    )
    if image_check.returncode != 0:
        raise EnvironmentBlockedError(
            f"品質用runtime imageがありません。初回セットアップを実行してください: {_RUNTIME_IMAGE}"
        )
    commands = _docker_commands(_RUNTIME_IMAGE)
    output: list[str] = []
    for command in commands:
        result = run_command(
            command,
            timeout_seconds=context.timeout_seconds,
            environment=context.environment,
        )
        output.append(result.output)
        if result.returncode != 0:
            return CommandResult(
                result.command,
                result.returncode,
                time.monotonic() - started,
                "".join(output),
                result.timed_out,
            )
    return CommandResult(
        commands[-1],
        0,
        time.monotonic() - started,
        "".join(output),
    )


def _e2e_action(context: RunContext, _: Path) -> CommandResult:
    """第二段階のReact・Streamlit共通E2Eを実行する。"""
    return run_e2e(
        base_environment=context.environment,
        artifact_directory=context.run_dir / "browser",
        timeout_seconds=context.timeout_seconds,
        visual_regression=context.profile == "deep",
    )


def _offline_guard_action(context: RunContext, _: Path) -> CommandResult:
    started = time.monotonic()
    forbidden = [
        key
        for key in context.environment
        if key.casefold().endswith(("api_key", "token", "password", "secret"))
        and context.environment[key]
    ]
    if forbidden:
        return CommandResult(
            ["offline-environment-check"],
            1,
            time.monotonic() - started,
            "秘密情報を含む環境変数が子processへ残っています: " + ", ".join(sorted(forbidden)),
        )
    mismatched = [
        key
        for key, expected in OFFLINE_GUARD_ENVIRONMENT.items()
        if context.environment.get(key) != expected
    ]
    if mismatched:
        return CommandResult(
            ["offline-environment-check"],
            1,
            time.monotonic() - started,
            "外部通信防止設定が一致しません: " + ", ".join(sorted(mismatched)),
        )
    return CommandResult(
        ["offline-environment-check"],
        0,
        time.monotonic() - started,
        "外部provider用の秘密情報とtelemetryを無効化しました。\n",
    )


def _profile_stages(
    profile: str,
    jobs: int,
    run_dir: Path | None = None,
    settings: QualitySettings | None = None,
) -> list[list[Gate]]:
    settings = settings or load_quality_settings()
    run_dir = run_dir or QUALITY_ROOT / "runs" / "unbound"
    pytest_workers = max(1, min(4, jobs))
    pytest_basetemp = TEMPORARY_ROOT / "pytest" / f"{os.getpid()}-{time.time_ns()}"
    quick_static = [
        Gate("ruff", "Python lint", _python("-m", "ruff", "check", "--no-cache", ".")),
        Gate(
            "format",
            "Python format",
            _python("-m", "ruff", "format", "--check", "--no-cache", "."),
        ),
        Gate(
            "docstrings",
            "Google style docstring",
            _python(
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--select",
                "D",
                "--ignore",
                "D100,D104,D203,D213,D400,D415",
                "src/werewolf_agent",
                "scripts",
            ),
        ),
        Gate(
            "mypy",
            "Python type check",
            _python(
                "-m",
                "mypy",
                "--no-incremental",
                "--cache-dir",
                str(TEMPORARY_ROOT / "mypy"),
                "src",
                "scripts",
            ),
        ),
        Gate(
            "import-linter",
            "Python import boundaries",
            _python_tool("lint-imports"),
        ),
        Gate("eslint", "Frontend lint", _npm("run", "lint"), cwd=REPOSITORY_ROOT / "frontend"),
        Gate(
            "prettier",
            "Frontend format",
            _npm("run", "format:check"),
            cwd=REPOSITORY_ROOT / "frontend",
        ),
        Gate(
            "typescript",
            "TypeScript type check",
            _npm("run", "typecheck"),
            cwd=REPOSITORY_ROOT / "frontend",
        ),
        Gate("vitest", "Frontend unit test", _npm("test"), cwd=REPOSITORY_ROOT / "frontend"),
        Gate(
            "offline",
            "Offline environment",
            ("offline-environment-check",),
            action=_offline_guard_action,
        ),
    ]
    stages = [
        quick_static,
        [
            Gate(
                "pytest",
                "Python quick test",
                _python(
                    "-m",
                    "pytest",
                    "--test-level=quick",
                    "-n",
                    str(pytest_workers),
                    "--dist",
                    "loadscope",
                    "--benchmark-disable",
                    "--junitxml",
                    str(run_dir / "test-results" / "quick.xml"),
                    "--basetemp",
                    str(pytest_basetemp),
                    "tests",
                ),
            )
        ],
    ]
    if profile == "quick":
        return stages

    if profile in {"release", "deep"}:
        stages.insert(
            0,
            [
                Gate(
                    "cleanup",
                    "Pre-release cleanup",
                    _python("-m", "scripts.quality", "clean"),
                    action=_cleanup_action,
                )
            ],
        )

    stages.extend(
        [
            [
                Gate(
                    "coverage",
                    "Python total and branch coverage",
                    tuple(_coverage_command(run_dir, settings)),
                    action=partial(_coverage_action, settings=settings),
                ),
                Gate(
                    "frontend-build",
                    "Frontend production build",
                    _npm("run", "build:quality"),
                    cwd=REPOSITORY_ROOT / "frontend",
                ),
                Gate(
                    "openapi",
                    "Generated OpenAPI contract",
                    _python("-m", "scripts.export_openapi"),
                    action=_openapi_action,
                ),
                Gate(
                    "docs",
                    "Sphinx warning-as-error build",
                    _docs_command(run_dir),
                    action=_docs_action,
                ),
                Gate(
                    "package",
                    "wheel, sdist and distribution contract",
                    _package_command(ARTIFACT_ROOT / "build" / "package"),
                    action=_package_action,
                ),
                Gate(
                    "benchmark",
                    "Core benchmark",
                    tuple(_benchmark_command(run_dir, settings)),
                    action=partial(_benchmark_action, settings=settings),
                ),
            ],
            [
                Gate(
                    "clean-tree",
                    "Tracked file unchanged",
                    ("git", "status", "--porcelain=v1"),
                    action=_clean_tree_action,
                )
            ],
        ]
    )
    if profile == "check":
        return stages

    stages.extend(
        [
            [
                Gate(
                    "supabase-preflight",
                    "Local Supabase preflight",
                    _python("-m", "scripts.preflight_supabase"),
                    action=_supabase_action,
                ),
            ],
            [
                Gate(
                    "integration",
                    "Package, Supabase and Streamlit integration",
                    _python(
                        "-m",
                        "pytest",
                        "--test-level=release",
                        "-m",
                        "not deep",
                        "-n",
                        "0",
                        "--junitxml",
                        str(run_dir / "test-results" / "integration.xml"),
                        "tests/integration",
                    ),
                ),
                Gate(
                    "e2e",
                    "React and Streamlit Playwright E2E",
                    _python("-m", "scripts.e2e"),
                    action=_e2e_action,
                ),
                Gate(
                    "docker",
                    "Docker non-root runtime",
                    tuple(_docker_commands(_RUNTIME_IMAGE)[0]),
                    action=_docker_action,
                ),
            ],
        ]
    )
    if profile == "release":
        return stages

    stages.append(
        [
            Gate(
                "deep-tests",
                "Failure injection and extended monkey tests",
                _python(
                    "-m",
                    "pytest",
                    "--test-level=deep",
                    "--confirm-deep",
                    "-m",
                    "deep",
                    "-n",
                    "0",
                    "--junitxml",
                    str(run_dir / "test-results" / "deep.xml"),
                    "tests",
                ),
            )
        ]
    )
    return stages


def clean(*, retention_days: int | None = None) -> list[Path]:
    """再生成可能な成果物と期限切れrunだけを削除する。"""
    if retention_days is None:
        retention_days = load_quality_settings().retention_days
    if retention_days < 0:
        raise ValueError("retention_daysには0以上を指定してください。")
    removed: list[Path] = []
    for path in BUILD_DIRECTORIES:
        if path.exists():
            remove_managed_path(path)
            removed.append(path)
    for path in TEMPORARY_CACHE_DIRECTORIES:
        if path.exists():
            remove_temporary_path(path)
            removed.append(path)

    cutoff = utc_now() - timedelta(days=retention_days)
    latest_id = None
    latest_path = QUALITY_ROOT / "latest.json"
    if latest_path.exists():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            latest = None
        if isinstance(latest, dict) and isinstance(latest.get("run_id"), str):
            latest_id = latest["run_id"]
    runs = QUALITY_ROOT / "runs"
    if runs.exists():
        run_directories = [run for run in runs.iterdir() if run.is_dir()]
        protected_ids = {latest_id} if latest_id is not None else set()
        if run_directories:
            newest = max(run_directories, key=lambda run: (run.stat().st_mtime, run.name))
            protected_ids.add(newest.name)
        for run in run_directories:
            if run.name in protected_ids:
                continue
            modified = utc_now().fromtimestamp(run.stat().st_mtime, tz=utc_now().tzinfo)
            if modified < cutoff:
                remove_managed_path(run)
                removed.append(run)
    return removed


def _run_gate(context: RunContext, gate: Gate) -> GateResult:
    log_path = context.run_dir / "logs" / f"{gate.name}.log"
    started = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as stream:
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
        state = _command_state(command_result, nonzero_state=gate.nonzero_state)
        message = "timeout" if command_result.timed_out else None
        return GateResult(
            name=gate.name,
            description=gate.description,
            state=state,
            duration_seconds=command_result.duration_seconds,
            command=command_result.command,
            returncode=command_result.returncode,
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
            message=message,
        )
    except EnvironmentBlockedError as error:
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        return GateResult(
            gate.name,
            gate.description,
            "blocked",
            time.monotonic() - started,
            command=list(gate.command),
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
            message=redact(str(error)),
        )
    except Exception as error:
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        return GateResult(
            gate.name,
            gate.description,
            "error",
            time.monotonic() - started,
            command=list(gate.command),
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
            message=redact(str(error)),
        )


def _command_state(result: CommandResult, *, nonzero_state: FailureState = "failed") -> State:
    """終了結果を品質違反と実行基盤異常へ分類する。"""
    if result.timed_out:
        return "error"
    if result.returncode == 0:
        return "passed"
    if _is_pytest_command(result.command) and result.returncode != 1:
        return "error"
    return nonzero_state


def _is_pytest_command(command: Sequence[str]) -> bool:
    """Python module形式のpytest commandか判定する。"""
    return any(
        tuple(command[index : index + 2]) == ("-m", "pytest")
        for index in range(max(0, len(command) - 1))
    )


def _write_summary(
    context: RunContext,
    results: list[GateResult],
) -> tuple[State, Path]:
    finished_at = utc_now()
    duration_seconds = (finished_at - context.started_at).total_seconds()
    report_path = context.run_dir / "report.json"
    metrics, artifact_issues = _collect_run_metrics(context.run_dir)
    artifact_issues.extend(
        _required_artifact_issues(
            context.profile,
            context.run_dir,
            started_at=context.started_at,
        )
    )
    if artifact_issues:
        artifact_result = GateResult(
            name="artifact-validation",
            description="Quality artifact validation",
            state="error",
            duration_seconds=0.0,
            message="; ".join(artifact_issues),
        )
        results.append(artifact_result)
        _append_events(context.run_dir / "events.jsonl", [artifact_result])
    state = _result_state(results)
    report = {
        "schema_version": 2,
        "run_id": context.run_id,
        "profile": context.profile,
        "state": state,
        "jobs": context.jobs,
        "started_at": context.started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "metrics": metrics,
        "artifact_issues": artifact_issues,
        "results": [asdict(result) for result in results],
    }
    write_json(report_path, report)
    summary = [
        f"# 品質評価: {context.profile}",
        "",
        f"- 判定: `{state}`",
        f"- Run ID: `{context.run_id}`",
        f"- 所要時間: `{duration_seconds:.2f}` 秒",
        "",
        "| Gate | 判定 | 秒 |",
        "| --- | --- | ---: |",
    ]
    summary.extend(
        f"| {result.description} | {result.state} | {result.duration_seconds:.2f} |"
        for result in results
    )
    summary.extend(_metric_summary(metrics, artifact_issues))
    problems = [result for result in results if result.state not in {"passed", "skipped"}]
    if problems:
        summary.extend(["", "## 調査対象", ""])
        for result in problems:
            detail = result.message or "詳細はログを確認してください。"
            log = f" (`{result.log}`)" if result.log else ""
            summary.append(f"- `{result.name}`: {detail}{log}")
    (context.run_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    write_latest(context.run_id, context.profile, state, report_path)
    return state, report_path


def _result_state(results: Sequence[GateResult]) -> State:
    """Gate結果から最上位状態を一貫した優先順位で返す。"""
    if any(result.state == "blocked" for result in results):
        return "blocked"
    if any(result.state == "error" for result in results):
        return "error"
    if any(result.state == "failed" for result in results):
        return "failed"
    return "passed"


def _collect_run_metrics(run_dir: Path) -> tuple[dict[str, object], list[str]]:
    """既存成果物からAIが直接比較できる指標を収集する。"""
    metrics: dict[str, object] = {"tests": {}, "browser_artifacts": []}
    issues: list[str] = []

    tests: dict[str, object] = {}
    for path in sorted((run_dir / "test-results").glob("*.xml")):
        try:
            all_suites = list(ET.parse(path).getroot().iter("testsuite"))
            suites = [
                suite
                for suite in all_suites
                if not any(child.tag == "testsuite" for child in suite)
            ]
            totals = {
                key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
                for key in ("tests", "failures", "errors", "skipped")
            }
            totals["passed"] = (
                totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
            )
            tests[path.stem] = totals
        except (ET.ParseError, OSError, ValueError) as error:
            issues.append(f"{path.name}を解析できません: {error}")
    metrics["tests"] = tests

    coverage_path = run_dir / "coverage" / "coverage.xml"
    if coverage_path.exists():
        try:
            coverage = ET.parse(coverage_path).getroot().attrib
            lines_valid = int(coverage["lines-valid"])
            lines_covered = int(coverage["lines-covered"])
            branches_valid = int(coverage["branches-valid"])
            branches_covered = int(coverage["branches-covered"])
            total_valid = lines_valid + branches_valid
            metrics["coverage"] = {
                "total_percent": round(
                    (lines_covered + branches_covered) / total_valid * 100,
                    2,
                )
                if total_valid
                else 100.0,
                "line_percent": round(float(coverage["line-rate"]) * 100, 2),
                "branch_percent": round(float(coverage["branch-rate"]) * 100, 2),
                "lines": {"covered": lines_covered, "valid": lines_valid},
                "branches": {"covered": branches_covered, "valid": branches_valid},
            }
        except (ET.ParseError, KeyError, OSError, ValueError) as error:
            issues.append(f"coverage.xmlを解析できません: {error}")

    benchmark_path = run_dir / "benchmarks" / "core.json"
    if benchmark_path.exists():
        try:
            document = json.loads(benchmark_path.read_text(encoding="utf-8"))
            benchmarks = document["benchmarks"]
            if not isinstance(benchmarks, list):
                raise ValueError("benchmarksが配列ではありません。")
            metrics["benchmarks"] = [
                {
                    "name": benchmark["name"],
                    "mean_ms": round(float(benchmark["stats"]["mean"]) * 1000, 3),
                    "rounds": int(benchmark["stats"]["rounds"]),
                }
                for benchmark in benchmarks
            ]
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            issues.append(f"core.jsonを解析できません: {error}")

    browser_root = run_dir / "browser"
    metrics["browser_artifacts"] = [
        path.relative_to(run_dir).as_posix()
        for path in sorted(browser_root.rglob("*"))
        if path.is_file()
    ]
    return metrics, issues


def _required_artifact_issues(
    profile: str,
    run_dir: Path,
    *,
    started_at: datetime | None = None,
) -> list[str]:
    """Profile必須成果物の欠落・重複・古い生成日時を返す。"""
    required = [run_dir / "test-results" / "quick.xml"]
    if profile in {"check", "release", "deep"}:
        required.extend(
            [
                run_dir / "test-results" / "coverage.xml",
                run_dir / "test-results" / "benchmark.xml",
                run_dir / "coverage" / ".coverage",
                run_dir / "coverage" / "coverage.xml",
                run_dir / "coverage" / "html" / "index.html",
                run_dir / "benchmarks" / "core.json",
                run_dir / "contracts" / "openapi.json",
                run_dir / "contracts" / "api.ts",
                ARTIFACT_ROOT / "build" / "docs" / "sphinx" / "index.html",
                ARTIFACT_ROOT / "build" / "frontend" / "index.html",
            ]
        )
    if profile in {"release", "deep"}:
        required.extend(
            [
                run_dir / "test-results" / "integration.xml",
            ]
        )
    if profile == "deep":
        required.append(run_dir / "test-results" / "deep.xml")

    issues = [
        f"必須成果物がありません: {_artifact_label(path, run_dir)}"
        for path in required
        if not path.is_file()
    ]
    if started_at is not None:
        started_timestamp = started_at.timestamp()
        issues.extend(
            f"必須成果物が現在runで更新されていません: {_artifact_label(path, run_dir)}"
            for path in required
            if path.is_file() and path.stat().st_mtime < started_timestamp
        )
    if profile in {"check", "release", "deep"}:
        package_root = ARTIFACT_ROOT / "build" / "package"
        for pattern, label in (("*.whl", "wheel"), ("*.tar.gz", "sdist")):
            packages = list(package_root.glob(pattern))
            count = len(packages)
            if count != 1:
                issues.append(f"{label}成果物は1件必要です: {count}件")
            elif started_at is not None and packages[0].stat().st_mtime < started_at.timestamp():
                issues.append(f"{label}成果物が現在runで更新されていません。")
    if profile in {"release", "deep"}:
        for name in ("desktop.png", "mobile.png"):
            matches = list((run_dir / "browser").rglob(name))
            if not matches:
                issues.append(f"browser成果物がありません: {name}")
            elif started_at is not None and all(
                path.stat().st_mtime < started_at.timestamp() for path in matches
            ):
                issues.append(f"browser成果物が現在runで更新されていません: {name}")
    return issues


def _artifact_label(path: Path, run_dir: Path) -> str:
    """必須成果物をrunまたは管理rootからの安定した相対名で返す。"""
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.relative_to(ARTIFACT_ROOT).as_posix()


def _metric_summary(metrics: dict[str, object], artifact_issues: list[str]) -> list[str]:
    """構造化指標を人間向けsummaryへ変換する。"""
    summary = ["", "## 指標", ""]
    tests = metrics.get("tests")
    if isinstance(tests, dict):
        for name, value in tests.items():
            if isinstance(value, dict):
                summary.append(
                    f"- `{name}`: {value.get('passed', 0)} passed, "
                    f"{value.get('failures', 0)} failed, "
                    f"{value.get('errors', 0)} errors, "
                    f"{value.get('skipped', 0)} skipped"
                )
    coverage = metrics.get("coverage")
    if isinstance(coverage, dict):
        summary.append(
            "- coverage: "
            f"total {coverage.get('total_percent')}%, "
            f"line {coverage.get('line_percent')}%, "
            f"branch {coverage.get('branch_percent')}%"
        )
    benchmarks = metrics.get("benchmarks")
    if isinstance(benchmarks, list):
        for benchmark in benchmarks:
            if isinstance(benchmark, dict):
                summary.append(
                    f"- benchmark `{benchmark.get('name')}`: "
                    f"mean {benchmark.get('mean_ms')}ms, "
                    f"{benchmark.get('rounds')} rounds"
                )
    browser_artifacts = metrics.get("browser_artifacts")
    if isinstance(browser_artifacts, list):
        summary.append(f"- browser artifacts: {len(browser_artifacts)} files")
    if artifact_issues:
        summary.extend(["", "### 成果物解析の問題", ""])
        summary.extend(f"- {issue}" for issue in artifact_issues)
    return summary


def _append_events(event_path: Path, results: Sequence[GateResult]) -> None:
    """完了または省略したgateを追記可能なeventとして保存する。"""
    with event_path.open("a", encoding="utf-8") as events:
        for result in results:
            events.write(
                json.dumps(
                    {
                        "event": "gate_completed",
                        "gate": result.name,
                        "state": result.state,
                        "duration_seconds": result.duration_seconds,
                        "timestamp": utc_now().isoformat(),
                        "message": result.message,
                        "log": result.log,
                    },
                    ensure_ascii=False,
                )
                + "\n"
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


def execute(
    profile: str,
    *,
    jobs: int,
    timeout_seconds: int,
    settings: QualitySettings | None = None,
) -> tuple[State, Path]:
    """指定profileのgateを段階ごとに並列実行する。"""
    run_id, run_dir = create_run_directory(profile)
    environment = quality_environment(run_dir=run_dir)
    context = RunContext(
        profile=profile,
        jobs=jobs,
        timeout_seconds=timeout_seconds,
        run_id=run_id,
        run_dir=run_dir,
        environment=environment,
        initial_git_status="",
        started_at=utc_now(),
    )
    results: list[GateResult] = []
    event_path = run_dir / "events.jsonl"
    settings = settings or load_quality_settings()
    stages = _profile_stages(profile, jobs, run_dir, settings)
    try:
        context.initial_git_status = _git_status(environment)
    except KeyboardInterrupt:
        message = "品質実行が初期化中に中断されました。"
        log_path = run_dir / "logs" / "runner-setup.log"
        log_path.write_text(message + "\n", encoding="utf-8")
        result = GateResult(
            "runner-setup",
            "Quality runner setup",
            "error",
            0.0,
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
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
        state, report_path = _write_summary(context, results)
        redact_artifacts(run_dir)
        return state, report_path
    except EnvironmentBlockedError as error:
        log_path = run_dir / "logs" / "runner-setup.log"
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        result = GateResult(
            "runner-setup",
            "Quality runner setup",
            "blocked",
            0.0,
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
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
        state, report_path = _write_summary(context, results)
        redact_artifacts(run_dir)
        return state, report_path
    except Exception as error:
        log_path = run_dir / "logs" / "runner-setup.log"
        log_path.write_text(redact(str(error)) + "\n", encoding="utf-8")
        result = GateResult(
            "runner-setup",
            "Quality runner setup",
            "error",
            0.0,
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
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
        state, report_path = _write_summary(context, results)
        redact_artifacts(run_dir)
        return state, report_path

    stopped_at: int | None = None
    try:
        for stage_index, stage in enumerate(stages):
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(jobs, len(stage))
            ) as executor:
                stage_results = list(executor.map(lambda gate: _run_gate(context, gate), stage))
            results.extend(stage_results)
            redact_artifacts(run_dir)
            _append_events(event_path, stage_results)
            if any(result.state != "passed" for result in stage_results):
                stopped_at = stage_index
                break

        if stopped_at is not None:
            skipped_results = _skipped_gate_results(
                stages[stopped_at + 1 :],
                message="前段の品質ゲートが完了しなかったため実行しませんでした。",
            )
            results.extend(skipped_results)
            _append_events(event_path, skipped_results)
    except KeyboardInterrupt:
        log_path = run_dir / "logs" / "runner.log"
        log_path.write_text("品質実行が中断されました。\n", encoding="utf-8")
        interrupted = GateResult(
            "runner",
            "Quality runner",
            "error",
            0.0,
            log=str(log_path.relative_to(REPOSITORY_ROOT)),
            message="品質実行が中断されました。",
        )
        results.append(interrupted)
        _append_events(event_path, [interrupted])
        completed = {result.name for result in results}
        skipped_results = _skipped_gate_results(
            stages,
            message="runnerが中断されたため完了を確認できませんでした。",
            completed=completed,
        )
        results.extend(skipped_results)
        _append_events(event_path, skipped_results)
    finally:
        if context.supabase_cleanup_required:
            stopped = _run_gate(
                context,
                Gate(
                    "supabase-stop",
                    "Stop quality-owned Supabase",
                    action=_supabase_stop_action,
                    timeout_seconds=60,
                    nonzero_state="error",
                ),
            )
            results.append(stopped)
            _append_events(event_path, [stopped])

    state, report_path = _write_summary(context, results)
    redact_artifacts(run_dir)
    return state, report_path


def build_parser(settings: QualitySettings | None = None) -> argparse.ArgumentParser:
    """コマンドライン引数を構築する。"""
    settings = settings or load_quality_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=(*PROFILE_ORDER, "clean"))
    parser.add_argument(
        "--jobs",
        type=lambda value: _bounded_positive_int(value, maximum=settings.max_jobs),
        default=min(settings.max_jobs, os.cpu_count() or 1),
    )
    parser.add_argument("--timeout", type=_positive_int)
    parser.add_argument("--confirm-deep", action="store_true")
    parser.add_argument(
        "--retention-days",
        type=_non_negative_int,
        default=settings.retention_days,
    )
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


def _non_negative_int(value: str) -> int:
    """0以上の整数をargparse向けに検証する。"""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("0以上の整数を指定してください。")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """品質profileまたはcleanupを実行する。"""
    try:
        settings = load_quality_settings()
    except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
        print(f"品質設定を読み込めません: {error}", file=sys.stderr)
        return 2
    arguments = build_parser(settings).parse_args(argv)
    if arguments.profile == "clean":
        try:
            removed = clean(retention_days=arguments.retention_days)
        except (OSError, ValueError) as error:
            print(f"成果物を削除できません: {error}", file=sys.stderr)
            return 2
        print(f"{len(removed)}件の再生成可能な成果物を削除しました。")
        return 0
    if arguments.profile == "deep" and not arguments.confirm_deep:
        print("deepの実行には--confirm-deepが必要です。", file=sys.stderr)
        return 2

    timeout = arguments.timeout or settings.timeouts[arguments.profile]
    state, report_path = execute(
        arguments.profile,
        jobs=arguments.jobs,
        timeout_seconds=timeout,
        settings=settings,
    )
    print(f"判定: {state}")
    print(f"レポート: {report_path}")
    if state == "passed":
        return 0
    if state in {"blocked", "error"}:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
