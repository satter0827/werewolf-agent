"""配布物と性能検査gate。"""

import json
import sys
import tarfile
import time
import tomllib
from functools import partial
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from scripts._infra.artifacts import LAYOUT, publish_directory, staged_directory
from scripts._infra.process import REPOSITORY_ROOT, CommandResult, run_command
from scripts.quality.models import Gate, QualitySettings, RunContext

PACKAGE_GATES = ("package",)
BENCHMARK_GATES = ("benchmark",)
GATES = (*PACKAGE_GATES, *BENCHMARK_GATES)


def build(run_dir: Path, settings: QualitySettings) -> list[Gate]:
    """配布物とbenchmarkのコマンド・成果物契約を返す。"""
    return [
        Gate(
            "package",
            "wheel, sdist and distribution contract",
            package_command(LAYOUT.build / "package"),
            action=build_package,
            artifacts=("build/package/*.whl", "build/package/*.tar.gz"),
        ),
        Gate(
            "benchmark",
            "Core benchmark",
            tuple(benchmark_command(run_dir, settings)),
            action=partial(run_benchmark, settings=settings),
            exclusive_resources=("benchmark",),
            artifacts=("benchmarks/core.json", "test-results/benchmark.xml"),
        ),
    ]


def python_command(*arguments: str) -> tuple[str, ...]:
    """現在のPythonでmoduleを実行するcommandを返す。"""
    return (sys.executable, *arguments)


def load_pyproject() -> dict[str, object]:
    """配布物契約の正本を読み込む。"""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def required_table(
    parent: dict[str, object],
    key: str,
    path: str,
) -> dict[str, object]:
    """必須TOML tableを返す。"""
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{path}をTOML tableとして定義してください。")
    return value


def build_package(context: RunContext, _: Path) -> CommandResult:
    """配布物を再構築し、公開entrypointと全resourceを検査する。"""
    started = time.monotonic()
    with staged_directory("package") as output_directory:
        command = package_command(output_directory)
        built = run_command(
            command,
            timeout_seconds=context.timeout_seconds,
            environment=context.environment,
        )
        output = [built.output]
        if built.returncode != 0:
            return built

        errors = distribution_contract_errors(output_directory)
        if errors:
            output.append("\n配布物契約に違反しています:\n")
            output.extend(f"- {error}\n" for error in errors)
            return CommandResult(
                command=list(command),
                returncode=1,
                duration_seconds=time.monotonic() - started,
                output="".join(output),
            )
        publish_directory(output_directory, LAYOUT.build / "package")
        output.append("\n配布物のentrypointと全resourceを確認しました。\n")
        return CommandResult(
            command=list(command),
            returncode=0,
            duration_seconds=time.monotonic() - started,
            output="".join(output),
        )


def package_command(output_directory: Path) -> tuple[str, ...]:
    """配布物を構築する固定commandを返す。"""
    return python_command(
        "-m",
        "build",
        "--no-isolation",
        "--outdir",
        str(output_directory),
    )


def distribution_contract_errors(output_directory: Path) -> list[str]:
    """構築済みwheelとsdistの公開契約違反を返す。"""
    packaged_resources, console_entrypoints = distribution_contract()
    wheels = sorted(output_directory.glob("*.whl"))
    source_distributions = sorted(output_directory.glob("*.tar.gz"))
    errors: list[str] = []
    if len(wheels) != 1:
        errors.append(f"wheelは1件必要です: {len(wheels)}件")
    if len(source_distributions) != 1:
        errors.append(f"sdistは1件必要です: {len(source_distributions)}件")
    elif source_distributions:
        errors.extend(sdist_contract_errors(source_distributions[0]))
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


def sdist_contract_errors(source_distribution: Path) -> list[str]:
    """sdistが設定された公開sourceを読める形で含むか検査する。"""
    try:
        with tarfile.open(source_distribution, mode="r:gz") as archive:
            names = {name.split("/", maxsplit=1)[1] for name in archive.getnames() if "/" in name}
    except (tarfile.TarError, OSError) as error:
        return [f"sdistを読み取れません: {error}"]

    errors: list[str] = []
    for source in sdist_contract():
        path = REPOSITORY_ROOT / source
        present = (
            source in names
            if path.is_file()
            else any(name.startswith(f"{source}/") for name in names)
        )
        if not present:
            errors.append(f"sdist sourceがありません: {source}")
    return errors


def sdist_contract() -> tuple[str, ...]:
    """pyproject.tomlからsdistに含めるsource契約を返す。"""
    document = load_pyproject()
    tool = required_table(document, "tool", "tool")
    hatch = required_table(tool, "hatch", "tool.hatch")
    build = required_table(hatch, "build", "tool.hatch.build")
    targets = required_table(build, "targets", "tool.hatch.build.targets")
    sdist = required_table(targets, "sdist", "tool.hatch.build.targets.sdist")
    only_include = sdist.get("only-include")
    if not isinstance(only_include, list) or not all(
        isinstance(value, str) and value for value in only_include
    ):
        raise ValueError("sdist.only-includeは空でない文字列の配列で指定してください。")
    return tuple(sorted(only_include))


def distribution_contract() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """pyproject.tomlからwheelのresourceとentrypoint契約を返す。"""
    document = load_pyproject()
    project = required_table(document, "project", "project")
    scripts = required_table(project, "scripts", "project.scripts")
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in scripts.items()):
        raise ValueError("project.scriptsは文字列の名前と参照先で指定してください。")
    source_path = REPOSITORY_ROOT / "src" / "werewolf_agent" / "resources"
    resources = [
        (Path("werewolf_agent/resources") / path.relative_to(source_path)).as_posix()
        for path in source_path.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    ]
    entrypoints = tuple(sorted(f"{name} = {value}" for name, value in scripts.items()))
    return tuple(sorted(resources)), entrypoints


def run_benchmark(
    context: RunContext,
    _: Path,
    *,
    settings: QualitySettings,
) -> CommandResult:
    """Core benchmarkを実行し、設定された性能上限を検査する。"""
    started = time.monotonic()
    result_path = context.run_dir / "benchmarks" / "core.json"
    command = benchmark_command(context.run_dir, settings)
    benchmark = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if benchmark.returncode != 0:
        return benchmark

    errors, measurements = benchmark_contract(
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


def benchmark_command(run_dir: Path, settings: QualitySettings) -> list[str]:
    """Core benchmarkの固定commandを返す。"""
    return list(
        python_command(
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
            "tests",
        )
    )


def benchmark_contract(
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


__all__ = [
    "BENCHMARK_GATES",
    "GATES",
    "PACKAGE_GATES",
    "benchmark_command",
    "benchmark_contract",
    "build",
    "build_package",
    "distribution_contract",
    "distribution_contract_errors",
    "package_command",
    "run_benchmark",
    "sdist_contract",
]
