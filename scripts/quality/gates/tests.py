"""Python unit・integration test gate。"""

import os
import sys
import time
import xml.etree.ElementTree as ET
from functools import partial
from pathlib import Path

from scripts._infra.process import TEMPORARY_ROOT, CommandResult, run_command
from scripts.quality.models import CPU_INTENSIVE_RESOURCE, Gate, QualitySettings, RunContext

UNIT_GATES = ("pytest",)
INTEGRATION_GATES = ("integration",)
COVERAGE_GATES: tuple[str, ...] = ()
DEEP_GATES = ("deep-tests", "deep-integration", "deep-supabase")
GATES = (*UNIT_GATES, *INTEGRATION_GATES, *COVERAGE_GATES, *DEEP_GATES)


def build(
    run_dir: Path,
    settings: QualitySettings,
    jobs: int,
    *,
    profile: str,
) -> list[Gate]:
    """pytestの選択規則と成果物契約を所有するtest gateを返す。"""
    python = sys.executable
    unit_profile = "check" if profile == "deep" else profile
    unit_command = pytest_command(run_dir, profile=unit_profile, jobs=jobs)
    unit_artifacts = [
        "test-results/unit.xml",
        "test-results/unit.json",
        "test-results/unit.html",
    ]
    if profile != "focus":
        unit_artifacts.extend(("coverage/coverage.xml", "coverage/html/index.html"))
    return [
        Gate(
            "pytest",
            "Python unit test with profile coverage",
            tuple(unit_command),
            action=partial(run_unit, profile=unit_profile, jobs=jobs),
            exclusive_resources=(CPU_INTENSIVE_RESOURCE,),
            artifacts=tuple(unit_artifacts),
        ),
        Gate(
            "integration",
            "Offline code integration",
            (
                python,
                "-m",
                "pytest",
                "--test-level=check",
                "-m",
                "not deep and not supabase",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "integration.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "integration.json"),
                "--html",
                str(run_dir / "test-results" / "integration.html"),
                "--self-contained-html",
                "tests/integration",
            ),
            dependencies=("package",),
            artifacts=(
                "test-results/integration.xml",
                "test-results/integration.json",
                "test-results/integration.html",
            ),
        ),
        Gate(
            "deep-tests",
            "Failure injection and extended domain tests",
            (
                python,
                "-m",
                "pytest",
                "--test-level=deep",
                "--confirm-deep",
                "-m",
                "monkey",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "deep.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "deep.json"),
                "--html",
                str(run_dir / "test-results" / "deep.html"),
                "--self-contained-html",
                "tests/unit",
            ),
            artifacts=(
                "test-results/deep.xml",
                "test-results/deep.json",
                "test-results/deep.html",
            ),
        ),
        Gate(
            "deep-integration",
            "Extended offline integration tests",
            (
                python,
                "-m",
                "pytest",
                "--test-level=deep",
                "--confirm-deep",
                "-m",
                "deep and not supabase",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "deep-integration.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "deep-integration.json"),
                "--html",
                str(run_dir / "test-results" / "deep-integration.html"),
                "--self-contained-html",
                "tests/integration",
            ),
            artifacts=(
                "test-results/deep-integration.xml",
                "test-results/deep-integration.json",
                "test-results/deep-integration.html",
            ),
        ),
        Gate(
            "deep-supabase",
            "Extended Supabase integration tests",
            (
                python,
                "-m",
                "pytest",
                "--test-level=deep",
                "--confirm-deep",
                "-m",
                "deep and supabase",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "deep-supabase.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "deep-supabase.json"),
                "--html",
                str(run_dir / "test-results" / "deep-supabase.html"),
                "--self-contained-html",
                "tests/integration/supabase",
            ),
            dependencies=("supabase-preflight",),
            exclusive_resources=("supabase",),
            artifacts=(
                "test-results/deep-supabase.xml",
                "test-results/deep-supabase.json",
                "test-results/deep-supabase.html",
            ),
        ),
    ]


def run_unit(
    context: RunContext,
    _: Path,
    *,
    profile: str,
    jobs: int,
) -> CommandResult:
    """Unit testを一度だけ実行し、check以上では同時にcoverageを採取する。"""
    started = time.monotonic()
    command = pytest_command(context.run_dir, profile=profile, jobs=jobs)
    result = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if result.returncode != 0 or profile == "focus":
        return result
    errors, branch_percentage = branch_coverage_contract(
        context.run_dir / "coverage" / "coverage.xml",
        minimum_percentage=0,
    )
    output = [result.output]
    if branch_percentage is not None:
        output.append(f"branch coverage: {branch_percentage:.2f}% (観測値)\n")
    if errors:
        output.append("branch coverage契約に違反しています:\n")
        output.extend(f"- {error}\n" for error in errors)
    return CommandResult(
        command,
        1 if errors else 0,
        time.monotonic() - started,
        "".join(output),
    )


def pytest_command(run_dir: Path, *, profile: str, jobs: int) -> list[str]:
    """Profileに応じた単一のunit test commandを返す。"""
    workers = max(1, min(4, jobs))
    basetemp = TEMPORARY_ROOT / "pytest" / f"{os.getpid()}-{time.time_ns()}"
    command = [
        sys.executable,
        "-m",
        "pytest",
        f"--test-level={profile}",
        "-n",
        str(workers),
        "--dist",
        "loadscope",
        "--benchmark-disable",
        "--junitxml",
        str(run_dir / "test-results" / "unit.xml"),
        "--json-report",
        "--json-report-file",
        str(run_dir / "test-results" / "unit.json"),
        "--html",
        str(run_dir / "test-results" / "unit.html"),
        "--self-contained-html",
        "--basetemp",
        str(basetemp),
    ]
    if profile != "focus":
        command.extend(
            (
                "--cov=werewolf_agent",
                "--cov-branch",
                "--cov-report",
                f"xml:{run_dir / 'coverage' / 'coverage.xml'}",
                "--cov-report",
                f"html:{run_dir / 'coverage' / 'html'}",
                "--cov-fail-under=0",
            )
        )
    command.extend(("tests/unit",))
    return command


def coverage_command(run_dir: Path, settings: QualitySettings) -> list[str]:
    """旧helper名からcheck用の統合commandを返す。"""
    del settings
    return pytest_command(run_dir, profile="check", jobs=1)


def run_coverage(
    context: RunContext,
    log_path: Path,
    *,
    settings: QualitySettings,
) -> CommandResult:
    """旧helper名からcheck用の統合実行を呼ぶ。"""
    del settings
    return run_unit(context, log_path, profile="check", jobs=1)


def branch_coverage_contract(
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


__all__ = [
    "COVERAGE_GATES",
    "DEEP_GATES",
    "GATES",
    "INTEGRATION_GATES",
    "UNIT_GATES",
    "branch_coverage_contract",
    "build",
    "coverage_command",
    "pytest_command",
    "run_coverage",
    "run_unit",
]
